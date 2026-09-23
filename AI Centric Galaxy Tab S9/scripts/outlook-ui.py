"""Bounded visible-screen reader for the linked tablet's Outlook app.

JSON on stdin/stdout. No arbitrary shell, coordinates, activities or editable
message actions are accepted. Outlook may mark opened messages as read.
"""
import datetime as dt
import base64
import hashlib
import json
import re
import shlex
import subprocess
import sys
import time
import os
import pathlib
import urllib.request
import xml.etree.ElementTree as ET

PACKAGE = 'com.microsoft.office.outlook'
PREFIX = PACKAGE + ':id/'
GALAXY = 'com.adamgoodwin.galaxyworkspace/.MainActivity'
DAYS = r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)'
EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')


def bounds(node):
    numbers = re.findall(r'-?\d+', node.get('bounds', ''))
    if len(numbers) != 4:
        raise ValueError('Outlook did not expose a usable element position.')
    return tuple(map(int, numbers))


def ref(node):
    keys = ['resource-id', 'text', 'content-desc', 'bounds', 'class']
    return hashlib.sha256(json.dumps([node.get(k, '') for k in keys]).encode()).hexdigest()[:24]


def readable(node):
    if node.get('package') != PACKAGE or node.get('enabled') != 'true':
        return False
    if node.get('clickable') != 'true':
        return False
    x1, y1, x2, y2 = bounds(node)
    if x2-x1 < 25 or y2-y1 < 25:
        return False
    if node.get('resource-id') == PREFIX + 'message_snippet_frontview':
        return True
    if node.get('resource-id') == PREFIX + 'message_open_details' and node.get('content-desc') == 'Open full message':
        return True
    if node.get('resource-id') == PREFIX + 'message_header' and node.get('content-desc', '').startswith('Message '):
        return True
    desc = node.get('content-desc', '')
    return bool(re.match(DAYS + r', ', desc) and
                (re.search(r'\d+:\d+\s*[ap]\.?m\.?', desc, re.I) or ', All Day,' in desc) and
                'Work location:' not in desc)


def forbidden(root):
    # Stop at credentials, a draft editor, or an unexpected app instead of
    # interpreting its text as a navigation instruction.
    for n in root.iter('node'):
        rid = n.get('resource-id', '').lower()
        if n.get('password') == 'true' or any(s in rid for s in [
                'compose_subject', 'compose_body', 'recipient_edit', 'compose_to']):
            raise ValueError('Outlook needs your attention. Close the sign-in or message editor and try again.')


def summary(root, clock):
    forbidden(root)
    nodes = [n for n in root.iter('node') if n.get('package') == PACKAGE]
    if not nodes:
        raise ValueError('Outlook is not visible. Unlock the tablet and open Outlook.')
    texts, seen = [], set()
    for n in nodes:
        # Use accessibility descriptions for grouped cards and plain text for
        # details. Never record keyboard input or other apps' window contents.
        value = n.get('content-desc') or n.get('text') or ''
        if value and value not in seen:
            seen.add(value)
            texts.append(value[:6000])
    text = '\n'.join(texts)
    items = [{'ref': ref(n), 'kind': 'email' if n.get('resource-id') in [PREFIX+'message_snippet_frontview', PREFIX+'message_open_details', PREFIX+'message_header'] else 'event',
              'label': (n.get('content-desc') or n.get('text') or '')[:2000]} for n in nodes if readable(n)]
    warnings = [t for t in texts if re.search(r'please sign in|sign in again|not connected|offline|couldn.t sync|unable to sync|fetching calendars|searching|loading', t, re.I)]
    if 'Open full message' in texts:
        warnings.append('The message is collapsed. Use its Open full message reference to read its body.')
    return {'deviceTime': clock, 'text': text[:28000], 'truncated': len(text) > 28000,
            'items': items[:30], 'warnings': warnings,
            'coverage': 'Visible Outlook screen only; current account/calendar selection and cached data. Not a complete mailbox or calendar export. Search results and message bodies may require more scrolling.'}


def account_choices(root):
    """Only choices inside Outlook's visible search-account popup are eligible."""
    choices = {}
    for listing in root.iter('node'):
        if listing.get('package') != PACKAGE or listing.get('class') != 'android.widget.ListView':
            continue
        for row in listing.findall('node'):
            if row.get('package') != PACKAGE or row.get('class') != 'android.widget.LinearLayout' or row.get('clickable') != 'true':
                continue
            titles = {n.get('text', '') for n in row.iter('node') if n.get('resource-id') == PREFIX + 'title'}
            if len(titles) != 1:
                continue
            title = next(iter(titles))
            if title != 'All Accounts' and not EMAIL.fullmatch(title):
                continue
            choices[title.casefold()] = (title, row)
    return choices


def selected_account(root):
    spinners = [n for n in root.iter('node') if n.get('package') == PACKAGE and n.get('resource-id') == PREFIX + 'account_spinner']
    if len(spinners) != 1:
        raise ValueError('Outlook did not show its search account. Open Mail search and try again.')
    match = re.fullmatch(r'Currently selected: (.*?), Select account to search', spinners[0].get('content-desc', ''))
    if not match:
        raise ValueError('Outlook did not identify the selected search account.')
    return match.group(1)


class Reader:
    def __init__(self, serial):
        if not re.fullmatch(r'[A-Za-z0-9._:-]{1,100}', serial):
            raise ValueError('Invalid linked tablet.')
        self.serial = serial
        self.warnings = set()

    def run(self, *args, timeout=14):
        result = subprocess.run(['adb', '-s', self.serial, *args], capture_output=True, timeout=timeout, check=True)
        if len(result.stdout) > 3_000_000:
            raise ValueError('Outlook screen is too large to read safely.')
        return result.stdout

    def shell(self, *args):
        return self.run('shell', ' '.join(shlex.quote(str(a)) for a in args)).decode('utf-8', errors='replace').strip()

    def foreground(self):
        lines = self.shell('dumpsys', 'window')
        focus = next((s for s in lines.splitlines() if 'mCurrentFocus=' in s), '')
        if PACKAGE not in focus:
            raise ValueError('Outlook lost focus. Return to Galaxy and try the request again.')

    def snapshot(self):
        self.foreground()
        # The one-shot instrumentation reader avoids Android's global idle
        # wait, which Outlook's continuous updates can prevent indefinitely.
        result = self.shell('am', 'instrument', '-w', '-r', 'com.adamgoodwin.galaxyreader/.OutlookSnapshot')
        error = re.search(r'^INSTRUMENTATION_RESULT: galaxy_error=(.*)$', result, re.M)
        if error:raise ValueError(error.group(1))
        encoded = re.search(r'^INSTRUMENTATION_RESULT: galaxy=([A-Za-z0-9+/=]+)$', result, re.M)
        if not encoded:
            raise ValueError('The tablet Outlook reader is unavailable. Install the Galaxy reader helper from the host.')
        raw = base64.b64decode(encoded.group(1), validate=True)
        if b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:
            raise ValueError('Unexpected Outlook screen format.')
        root = ET.fromstring(raw)
        forbidden(root)
        for n in root.iter('node'):
            value=n.get('text') or n.get('content-desc') or ''
            if re.search(r'please sign in|sign in again|not connected|offline|couldn.t sync|unable to sync',value,re.I):self.warnings.add(value)
        return root

    def find(self, root, key, value):
        found = [n for n in root.iter('node') if n.get('package') == PACKAGE and n.get(key) == value]
        if len(found) != 1:
            raise ValueError('Outlook control unavailable: '+value.split(':id/')[-1]+'. Open Outlook Mail or Calendar and try again.')
        return found[0]

    def tap(self, node):
        self.foreground()
        x1, y1, x2, y2 = bounds(node)
        if x2 <= x1 or y2 <= y1:
            raise ValueError('Outlook control is off screen.')
        self.shell('input', 'tap', (x1+x2)//2, (y1+y2)//2)
        time.sleep(.25)

    def picker_choices(self, expected=None):
        # Outlook populates its account popup after the opening animation.
        # The selected account may also be below the visible picker rows.
        root, choices, seen = None, {}, {}
        for page in range(3):
            for attempt in range(6):
                root = self.snapshot()
                choices = account_choices(root)
                seen.update(choices)
                if expected and expected.casefold() in choices:
                    return root, choices
                if attempt < 5:
                    time.sleep(.35)
            if page == 2 or not self.scroll_account_picker(root):
                break
        return root, choices if expected else seen

    def scroll_account_picker(self, root):
        lists = [n for n in root.iter('node') if n.get('package') == PACKAGE and
                 n.get('class') == 'android.widget.ListView' and n.get('scrollable') == 'true' and
                 account_choices(n)]
        if len(lists) != 1:
            return False
        x1, y1, x2, y2 = bounds(lists[0])
        if x2-x1 < 100 or y2-y1 < 200:
            return False
        self.foreground()
        self.shell('input', 'swipe', (x1+x2)//2, y2-80, (x1+x2)//2, y1+80, 320)
        time.sleep(.35)
        return True

    def search_button(self):
        root = self.root('Mail')
        for attempt in range(5):
            buttons = [n for n in root.iter('node') if n.get('package') == PACKAGE and n.get('content-desc') == 'Search']
            if len(buttons) == 1:
                return root, buttons[0]
            if attempt < 4:
                time.sleep(.35)
                root = self.snapshot()
        raise ValueError('Outlook Mail did not show Search. Keep the tablet unlocked and try again.')

    def root(self, section):
        root = self.snapshot()
        for _ in range(5):
            if any(n.get('resource-id') == PREFIX+'central_toolbar' for n in root.iter('node')) and not any(n.get('resource-id') == PREFIX+'search_edit_text' for n in root.iter('node')):
                options = [n for n in root.iter('node') if n.get('content-desc') == section]
                if len(options) == 1:
                    if options[0].get('clickable') == 'true':
                        self.tap(options[0]);root = self.snapshot()
                    return root
                menu = [n for n in root.iter('node') if n.get('content-desc') == 'Open Navigation Drawer']
                if len(menu) == 1:
                    self.tap(menu[0]);root = self.snapshot();continue
            self.foreground();self.shell('input', 'keyevent', '4');time.sleep(.4);root = self.snapshot()
        raise ValueError('Could not reach Outlook navigation. Open its Mail or Calendar tab and try again.')

    def scroll(self, root, direction):
        candidates = [n for n in root.iter('node') if n.get('package') == PACKAGE and n.get('scrollable') == 'true' and n.get('resource-id') in [PREFIX+'agenda_view', PREFIX+'recycler_view', PREFIX+'conversation_list', PREFIX+'conversations_recycler_view', PREFIX+'message_details_nested_scrolling_recycler_view']]
        message = [n for n in candidates if n.get('resource-id')==PREFIX+'message_details_nested_scrolling_recycler_view'] or [n for n in candidates if n.get('resource-id')==PREFIX+'conversations_recycler_view']
        if message:candidates=message
        if not candidates:
            # The selected message body is a WebView. Its scrollable children
            # are eligible, but never the account drawer or notification panel.
            seen=set()
            for n in root.iter('node'):
                if n in seen:continue
                if n.get('class') == 'android.webkit.WebView' and n.get('package') == PACKAGE:
                    seen.update(n.iter('node'))
                    a,b,c,d=bounds(n)
                    for child in n.iter('node'):
                        if child.get('scrollable')!='true':continue
                        x1,y1,x2,y2=bounds(child)
                        clipped=ET.Element('node',child.attrib)
                        clipped.set('bounds',f'[{max(a,x1)},{max(b,y1)}][{min(c,x2)},{min(d,y2)}]')
                        candidates.append(clipped)
        if not candidates:
            raise ValueError('No readable Outlook list or message body is available to scroll.')
        n = max(candidates, key=lambda n:(bounds(n)[2]-bounds(n)[0])*(bounds(n)[3]-bounds(n)[1]))
        x1,y1,x2,y2 = bounds(n);x=(x1+x2)//2;top=y1+max(30,(y2-y1)//5);bottom=y2-max(30,(y2-y1)//5)
        if x2-x1 < 80 or bottom-top < 80:raise ValueError('No usable content area to scroll. Close the keyboard and read the screen again.')
        self.foreground();self.shell('input','swipe',x,bottom if direction=='down' else top,x,top if direction=='down' else bottom,350)

    def execute(self, data):
        op = data.get('operation')
        if op == 'return':
            try:self.foreground()
            except ValueError:return {'returned': False}
            self.shell('am','start','--activity-reorder-to-front','--activity-single-top','-n',GALAXY)
            return {'returned': True}
        if op not in ['accounts','calendar','search','read','open','scroll','back']:
            raise ValueError('Unsupported Outlook reading action.')
        if op == 'calendar' and (type(data.get('dayOffset',0)) != int or not -7 <= data.get('dayOffset',0) <= 14):
            raise ValueError('Choose a day from last week through the next two weeks.')
        if op == 'search' and (not isinstance(data.get('query'),str) or not re.fullmatch(r'[A-Za-z0-9 @._:+\-]{1,120}',data['query']) or not data['query'].strip()):
            raise ValueError('Use a short search with letters, numbers, spaces, @, dots, colons or hyphens.')
        if op == 'search' and 'account' in data and (not isinstance(data['account'], str) or (data['account'] != 'all' and not EMAIL.fullmatch(data['account']))):
            raise ValueError('Choose an exact Outlook account address or all accounts.')
        if op == 'open' and (not isinstance(data.get('ref'),str) or not re.fullmatch(r'[a-f0-9]{24}',data['ref'])):
            raise ValueError('Use a fresh item reference from the Outlook reader.')
        if op == 'scroll' and data.get('direction') not in ['up','down']:
            raise ValueError('Choose up or down.')
        # Keep a full-message activity open between operations. Relaunching
        # MainActivity here would silently collapse it before scroll/read.
        try:self.foreground()
        except ValueError:self.shell('am','start','--activity-reorder-to-front','--activity-single-top','-n',PACKAGE+'/.MainActivity')
        for attempt in range(15):
            try:self.foreground();break
            except ValueError:
                if attempt==14:raise
                time.sleep(.2)
        root = self.snapshot()
        if op == 'calendar':
            offset = data.get('dayOffset',0)
            if type(offset) != int or not -7 <= offset <= 14:raise ValueError('Choose a day from last week through the next two weeks.')
            root = self.root('Calendar')
            view = self.find(root,'resource-id',PREFIX+'menu_calendar_views')
            if 'Agenda' not in view.get('content-desc',''):
                self.tap(view);root=self.snapshot();self.tap(self.find(root,'text','Agenda'));root=self.snapshot()
            device_date = self.shell('date','+%Y-%m-%d')
            target = dt.date.fromisoformat(device_date)+dt.timedelta(days=offset)
            self.tap(self.find(root,'resource-id',PREFIX+'calendar_month_title_button'));root=self.snapshot()
            label = target.strftime('%A, %B ') + str(target.day)
            found = [n for n in root.iter('node') if n.get('clickable')=='true' and re.sub(r'^Events on ', '', n.get('content-desc','')).split(', today')[0].split(', Selected')[0] == label]
            if len(found)!=1:raise ValueError('That date is outside the visible Outlook date picker. Select the day in Outlook and use Read current screen.')
            self.tap(found[0]);root=self.snapshot()
        elif op == 'accounts':
            root, button = self.search_button()
            self.tap(button);root=self.snapshot()
            current = selected_account(root)
            self.tap(self.find(root,'resource-id',PREFIX+'account_spinner'))
            root, choices = self.picker_choices()
            if not choices:raise ValueError('Outlook did not show readable account choices. Select an account in Outlook and try again.')
            return {'accounts': [email for email, _ in choices.values() if email != 'All Accounts'],
                    'selectedAccount': current, 'text': 'Visible Outlook search accounts: ' + ', '.join(email for email, _ in choices.values() if email != 'All Accounts'),
                    'coverage': 'Visible account choices in Outlook Mail search; other accounts may require scrolling.',
                    'warnings': []}
        elif op == 'search':
            query=data.get('query','')
            if not isinstance(query,str) or not re.fullmatch(r'[A-Za-z0-9 @._:+\-]{1,120}',query) or not query.strip():
                raise ValueError('Use a short search with letters, numbers, spaces, @, dots, colons or hyphens.')
            root, button = self.search_button()
            self.tap(button);root=self.snapshot()
            clear=[n for n in root.iter('node') if n.get('resource-id')==PREFIX+'search_cancel_btn']
            if clear:self.tap(clear[0]);root=self.snapshot()
            requested=data.get('account')
            if requested:
                target='All Accounts' if requested=='all' else requested
                if selected_account(root).casefold()!=target.casefold():
                    self.tap(self.find(root,'resource-id',PREFIX+'account_spinner'))
                    root,choices=self.picker_choices(target)
                    choice=choices.get(target.casefold())
                    if not choice:raise ValueError('The requested Outlook account is not visible in the search picker. Choose it in Outlook and try again.')
                    self.tap(choice[1]);root=self.snapshot()
                if selected_account(root).casefold()!=target.casefold():
                    raise ValueError('Outlook did not switch to the requested account. No search was submitted.')
            scope=selected_account(root)
            # Warnings seen while navigating from a different mailbox do not
            # describe the account whose search is about to run.
            if requested:self.warnings.clear()
            self.tap(self.find(root,'resource-id',PREFIX+'search_edit_text'))
            self.shell('input','text',query.replace(' ','%s'));self.shell('input','keyevent','66');root=self.snapshot()
            if self.find(root,'resource-id',PREFIX+'search_edit_text').get('text')!=query:raise ValueError('Outlook did not accept the exact search. No results were captured.')
            # Outlook's All results expose complete accessible message cards;
            # this tablet's newer Mail-only results expose blank row semantics.
            filters=[n for n in root.iter('node') if n.get('content-desc')=='All' and any(x.get('resource-id')=='android:id/text1' for x in n.iter('node'))]
            if len(filters)==1 and filters[0].get('clickable')=='true':self.tap(filters[0]);root=self.snapshot()
            # Samsung's keyboard can consume Enter without submitting, and
            # changing the filter can reopen suggestions. Submit after filtering.
            # Only tap the exact text-search suggestion, never a person/message.
            suggestions=[n for n in root.iter('node') if n.get('package')==PACKAGE and n.get('clickable')=='true' and n.get('content-desc')=='Suggested search , Text, Search for "'+query+'"']
            if len(suggestions)==1:
                self.tap(suggestions[0]);time.sleep(.7);root=self.snapshot()
            # Allow a bounded refresh; an unfinished search stays explicitly
            # incomplete rather than being presented as an empty mailbox.
            for _ in range(4):
                text=' '.join(n.get('text','')+' '+n.get('content-desc','') for n in root.iter('node'))
                if not re.search(r'Suggested search|Searching|Loading',text,re.I):break
                time.sleep(.5);root=self.snapshot()
        elif op == 'open':
            chosen=[n for n in root.iter('node') if readable(n) and ref(n)==data.get('ref')]
            if len(chosen)!=1:raise ValueError('That Outlook item moved or changed. Read the screen again before opening it.')
            self.tap(chosen[0]);root=self.snapshot()
        elif op == 'scroll':
            if data.get('direction') not in ['up','down']:raise ValueError('Choose up or down.')
            self.scroll(root,data['direction']);root=self.snapshot()
        elif op == 'back':
            self.foreground();self.shell('input','keyevent','4');time.sleep(.4);root=self.snapshot()
        result=summary(root,self.shell('date','+%Y-%m-%dT%H:%M:%S%z'))
        result['warnings']=list(dict.fromkeys(result['warnings']+sorted(self.warnings)))
        if op=='calendar':result['requestedDate']=target.isoformat()
        if op=='search':
            result['query']=query
            result['selectedAccount']=scope
            result['searchSubmitted']=not any(n.get('resource-id')==PREFIX+'suggestion_text' and n.get('text')=='Search for "'+query+'"' for n in root.iter('node'))
            if not result['searchSubmitted']:result['warnings'].append('Outlook still shows a search suggestion. The search has not completed; these are not search results.')
        return result


class NativeReader(Reader):
    """The same bounded reading workflow, using local Android APIs instead of ADB."""
    def call(self, operation, **fields):
        state=pathlib.Path(os.environ.get('GALAXY_STATE_DIR', pathlib.Path(__file__).resolve().parent.parent/'.local'))
        key=(state/'device-bridge.key').read_text()
        if not re.fullmatch('[a-f0-9]{64}',key):raise ValueError('Device tools are not configured.')
        request=urllib.request.Request('http://127.0.0.1:48442/device',
            data=json.dumps({'operation':operation,**fields}).encode(),
            headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=7) as response:
                raw=response.read(700001)
            if len(raw)>700000:raise ValueError('Device response exceeded its limit.')
            data=json.loads(raw)
        except (OSError, json.JSONDecodeError):
            raise ValueError('Enable Galaxy Device Tools in Android Accessibility settings, then try again.') from None
        if data.get('error'):raise ValueError(data['error'])
        return data['result']

    def run(self,*args,**kwargs):
        raise ValueError('ADB is not used by the on-device reader.')

    def foreground(self):self.call('foreground')

    def snapshot(self):
        raw=self.call('snapshot')['xml'].encode()
        if b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:raise ValueError('Unexpected Outlook screen format.')
        root=ET.fromstring(raw);forbidden(root)
        for n in root.iter('node'):
            value=n.get('text') or n.get('content-desc') or ''
            if re.search(r'please sign in|sign in again|not connected|offline|couldn.t sync|unable to sync',value,re.I):self.warnings.add(value)
        return root

    def tap(self,node):
        self.call('tap',node=dict(node.attrib));time.sleep(.25)

    def scroll(self,root,direction):
        self.call('scroll',direction=direction);time.sleep(.25)

    def scroll_account_picker(self,root):
        scrolled=self.call('account_scroll').get('scrolled',False)
        if scrolled:time.sleep(.35)
        return scrolled

    def shell(self,*args):
        if args[0]=='date':return dt.datetime.now().astimezone().strftime(args[1].removeprefix('+'))
        if args[:2]==('am','start'):
            if args[-1]==GALAXY:self.call('return')
            elif args[-1]==PACKAGE+'/.MainActivity':self.call('open')
            else:raise ValueError('Unsupported app.')
        elif args[:2]==('input','text'):self.call('search_text',query=args[2].replace('%s',' '))
        elif args==('input','keyevent','66'):self.call('enter')
        elif args==('input','keyevent','4'):self.call('back')
        else:raise ValueError('Unsupported on-device navigation.')
        return ''

def main():
    data=json.loads(sys.stdin.read(20000))
    reader=(NativeReader if os.environ.get('GALAXY_RUNTIME')=='android' else Reader)(data.get('serial',''))
    try:
        print(json.dumps(reader.execute(data)))
    except (ValueError,ET.ParseError,subprocess.SubprocessError) as error:
        # Never echo subprocess arguments or captured private UI content.
        message=str(error) if isinstance(error,ValueError) else 'Outlook could not be read reliably. Keep the tablet unlocked, wait for Outlook to settle, and try again.'
        print(json.dumps({'error':message}));sys.exit(1)

if __name__ == '__main__':main()
