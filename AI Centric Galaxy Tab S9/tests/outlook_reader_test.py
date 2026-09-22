import unittest,importlib.util,xml.etree.ElementTree as E
spec=importlib.util.spec_from_file_location('reader','scripts/outlook-ui.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def node(**changes):
 attrs={'package':m.PACKAGE,'enabled':'true','clickable':'true','bounds':'[200,300][1000,500]','resource-id':m.PREFIX+'message_snippet_frontview','content-desc':'Council meeting','class':'android.view.View'};attrs.update(changes);return E.Element('node',attrs)
class ReaderTests(unittest.TestCase):
 def test_readable_limits(self):
  self.assertTrue(m.readable(node()))
  self.assertFalse(m.readable(node(**{'resource-id':m.PREFIX+'send','content-desc':'Send'})))
  self.assertFalse(m.readable(node(**{'resource-id':'','content-desc':'Accept invitation'})))
  self.assertTrue(m.readable(node(**{'resource-id':m.PREFIX+'message_open_details','content-desc':'Open full message'})))
  self.assertFalse(m.readable(node(**{'resource-id':m.PREFIX+'message_open_details','content-desc':'Edit RSVP'})))
  self.assertFalse(m.readable(node(package='other.app')))
  self.assertFalse(m.readable(node(bounds='[10,10][12,12]')))
  self.assertTrue(m.readable(node(**{'resource-id':'','content-desc':'Tuesday, September 22, 10:00 a.m. to 11:00 a.m., Council'})))
  self.assertFalse(m.readable(node(**{'resource-id':'','content-desc':'Tuesday, September 22, Work location: Home'})))
 def test_reference_changes(self):
  a=node();self.assertNotEqual(m.ref(a),m.ref(node(**{'content-desc':'Changed message'})));self.assertNotEqual(m.ref(a),m.ref(node(bounds='[200,500][1000,700]')))
 def test_password_and_warnings(self):
  root=E.Element('hierarchy');root.append(node(**{'text':'Please sign in to Council.','content-desc':''}))
  self.assertIn('Please sign in to Council.',m.summary(root,'now')['warnings'])
  root.append(node(password='true'))
  with self.assertRaises(ValueError):m.summary(root,'now')
 def test_bad_inputs_and_fresh_snapshot(self):
  with self.assertRaises(ValueError):m.Reader('bad;serial')
  r=m.Reader('fixture');r.foreground=lambda:None;r.shell=lambda *args:'INSTRUMENTATION_RESULT: galaxy_error=locked'
  with self.assertRaisesRegex(ValueError,'locked'):r.snapshot()
  with self.assertRaises(ValueError):r.execute({'operation':'send'})
  for data in [{'operation':'search','query':'$(id)'},{'operation':'calendar','dayOffset':100},{'operation':'open','ref':'Send'},{'operation':'scroll','direction':'left'}]:
   with self.assertRaises(ValueError):r.execute(data)
 def test_read_keeps_current_outlook_activity(self):
  r=m.Reader('fixture');calls=[];root=E.Element('hierarchy');root.append(node())
  r.foreground=lambda:None;r.snapshot=lambda:root
  r.shell=lambda *args:calls.append(args) or '2026-09-21T23:00:00-0600'
  r.execute({'operation':'read'})
  self.assertFalse(any(args[0]=='am' for args in calls))
 def test_scroll_stays_inside_expanded_message(self):
  r=m.Reader('fixture');r.foreground=lambda:None;calls=[];r.shell=lambda *args:calls.append(args)
  root=E.Element('hierarchy');root.append(node(**{'resource-id':m.PREFIX+'recycler_view','scrollable':'true','bounds':'[0,0][2000,1400]'}));root.append(node(**{'resource-id':m.PREFIX+'message_details_nested_scrolling_recycler_view','scrollable':'true','bounds':'[800,250][1980,1490]'}))
  r.scroll(root,'down');swipe=calls[-1];self.assertEqual(swipe[:2],('input','swipe'));self.assertGreater(swipe[3],250);self.assertLess(swipe[3],1490);self.assertGreater(swipe[2],800)
class NativeReaderTests(unittest.TestCase):
 def test_never_runs_adb_or_arbitrary_apps(self):
  r=m.NativeReader('native');calls=[];r.call=lambda op,**fields:calls.append((op,fields)) or {}
  with self.assertRaisesRegex(ValueError,'ADB'):r.run('shell','id')
  for args in [('sh','-c','id'),('am','start','-n','other.app'),('input','tap','1','2')]:
   with self.assertRaises(ValueError):r.shell(*args)
  r.shell('am','start','-n',m.PACKAGE+'/.MainActivity')
  r.shell('input','text','Council%smeeting')
  r.shell('input','keyevent','66')
  self.assertEqual([c[0] for c in calls],['open','search_text','enter'])
  self.assertEqual(calls[1][1],{'query':'Council meeting'})
 def test_native_snapshot_checks_passwords_and_preserves_warning(self):
  r=m.NativeReader('native');root=E.Element('hierarchy');root.append(node(text='Please sign in again'))
  r.call=lambda *args,**kw:{'xml':E.tostring(root).decode()}
  r.snapshot();self.assertIn('Please sign in again',r.warnings)
  root.append(node(password='true'))
  with self.assertRaises(ValueError):r.snapshot()
if __name__=='__main__':unittest.main()
