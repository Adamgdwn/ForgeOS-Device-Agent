"""Run the bridge's emitted YTM player expressions against a fake DOM."""
import json
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]
SOURCE = ((ROOT / "appliance/native/music_bridge.c").read_text() + "\n" +
          (ROOT / "appliance/native/music_bridge_ui_maintenance.h").read_text())


def c_strings(text):
    return "".join(json.loads(token) for token in re.findall(r'"(?:\\.|[^"\\])*"', text))


def constant(name):
    match = re.search(rf"static const char {name}\[\] =\s*((?:\"(?:\\.|[^\"\\])*\"\s*)+);", SOURCE, re.S)
    assert match, name
    return c_strings(match.group(1))


def operation(action):
    prefix = rf'!strcmp\(action, "{action}"\)\)\s*'
    strings = r'((?:\"(?:\\.|[^\"\\])*\"\s*)+)'
    if action == "VOLUME":
        match = re.search(prefix + r'snprintf\(operation, sizeof operation,\s*' + strings + r', volume\);', SOURCE, re.S)
    else:
        match = re.search(prefix + r'strcpy\(operation,\s*' + strings + r'\);', SOURCE, re.S)
    assert match, action
    return c_strings(match.group(1)).replace("%u", "22")


def next_expression():
    return constant("ACTION_PREFIX") + operation("NEXT") + constant("ACTION_SUFFIX")


def test_generated_js_uses_only_cast_aware_ytm_facade():
    node = shutil.which("node")
    assert node, "node is required for the bridge JavaScript behavior test"
    expressions = {
        "state": constant("STATE"),
        "play": constant("ACTION_PREFIX") + operation("PLAY") + constant("ACTION_SUFFIX"),
        "pause": constant("ACTION_PREFIX") + operation("PAUSE") + constant("ACTION_SUFFIX"),
        "rewind": constant("ACTION_PREFIX") + operation("REWIND") + constant("ACTION_SUFFIX"),
        "volume": constant("ACTION_PREFIX") + operation("VOLUME") + constant("ACTION_SUFFIX"),
        "next": constant("ACTION_PREFIX") + operation("NEXT") + constant("ACTION_SUFFIX"),
    }
    script = r'''
const vm=require('vm'), x=JSON.parse(process.argv[1]);
let calls=[], local={get paused(){throw Error('local video read')}, play(){throw Error('local play')}};
let p={getPlayerState:()=>3,getCurrentTime:()=>12.5,getVolume:()=>31,
 getVideoData:()=>({title:'Cast \u266b Song',author:'Artist',video_id:'current0000'}),
 getOption:(a,b)=>b==='casting'?true:{name:'Main \u2603 Speakers'},
 playVideo:()=>calls.push('play'),pauseVideo:()=>calls.push('pause'),seekTo:(n)=>calls.push('seek:'+n),
 setVolume:(n)=>calls.push('volume:'+n),nextVideo:()=>{throw Error('generic Next bypasses YTM queue')}};
let automix=[], root={querySelectorAll:q=>q==='#automix-contents ytmusic-player-queue-item'?automix:[]};
const item=(index,selected,videoId)=>({hasAttribute:a=>a==='selected'&&selected,closest:q=>q==='ytmusic-player-queue'?root:null,
 data:{navigationEndpoint:{watchEndpoint:{index,playlistId:'owned-queue',videoId}}},
 resolveCommand:e=>{if(e.watchEndpoint.index!==3)throw Error('wrong queue item');calls.push('next')}});
const queue=[item(2,true,'current0000'),item(2,false,'variant0000'),item(3,false,'nextsong000'),item(3,false,'alternate00'),item(4,false,'latersong00')];
const hiddenQueue=[item(7,true,'hidden00000')];
const alternateSelected=item(2,true,'other000000');
let ctx={location:{origin:'https://music.youtube.com'},document:{querySelector:q=>q==='#movie_player'?p:(q==='video'?local:null),querySelectorAll:q=>q==='ytmusic-player-queue ytmusic-player-queue-item'?[...queue,alternateSelected]:q.includes('ytmusic-player-queue-item')?[...queue,...hiddenQueue]:[]}};
(async()=>{let state=await vm.runInNewContext(x.state,ctx); for(const k of ['play','pause','rewind','volume','next']) await vm.runInNewContext(x[k],ctx); console.log(JSON.stringify({state,calls}))})().catch(e=>{console.error(e);process.exit(1)});
'''
    run = subprocess.run([node, "-e", script, json.dumps(expressions)], text=True, capture_output=True, check=True)
    result = json.loads(run.stdout)
    assert result["state"] == "0\t600000\t31\tCast   Song\tArtist\tMain   Speakers\tBUFFERING\tcurrent0000"
    assert result["calls"] == ["play", "pause", "pause", "seek:0", "volume:22", "next"]


def test_next_uses_scoped_automix_after_a_search_seed():
    script = r'''
const vm=require('vm'), expression=process.argv[1], calls=[];
const root={querySelectorAll:q=>q==='#automix-contents ytmusic-player-queue-item'?[next,counterpart]:[]};
const seed={hasAttribute:a=>a==='selected',closest:q=>q==='ytmusic-player-queue'?root:null,
 data:{navigationEndpoint:{watchEndpoint:{index:0,videoId:'seedvideo00'}}}};
const next={data:{navigationEndpoint:{watchEndpoint:{index:1,playlistId:'RDseedqueue',videoId:'nextsong000'}}},
 resolveCommand:e=>{if(e!==next.data.navigationEndpoint)throw Error('endpoint');calls.push('automix')}};
const counterpart={data:{navigationEndpoint:{watchEndpoint:{index:1,playlistId:'RDseedqueue',videoId:'alternate00'}}},
 closest:q=>q==='#counterpart-renderer'?{}:null,
 resolveCommand:()=>{throw Error('hidden audio/video counterpart must not duplicate next')}};
const p={getVideoData:()=>({video_id:'seedvideo00'})};
const ctx={location:{origin:'https://music.youtube.com'},document:{querySelector:q=>q==='#movie_player'?p:null,
 querySelectorAll:q=>q==='ytmusic-player-queue ytmusic-player-queue-item'?[seed]:[]}};
vm.runInNewContext(expression,ctx).then(()=>console.log(JSON.stringify(calls))).catch(e=>{console.error(e);process.exit(1)});
'''
    run = subprocess.run([shutil.which("node"), "-e", script, next_expression()],
                         text=True, capture_output=True, check=True)
    assert json.loads(run.stdout) == ["automix"]


def test_next_rejects_missing_or_ambiguous_automix_candidates():
    script = r'''
const vm=require('vm'), expression=process.argv[1];
const candidate=(id)=>({data:{navigationEndpoint:{watchEndpoint:{index:1,playlistId:'RDseedqueue',videoId:id}}},resolveCommand:()=>{throw Error('must not navigate')}});
async function attempt(rows) {
 const root={querySelectorAll:q=>q==='#automix-contents ytmusic-player-queue-item'?rows:[]};
 const seed={hasAttribute:a=>a==='selected',closest:q=>q==='ytmusic-player-queue'?root:null,data:{navigationEndpoint:{watchEndpoint:{index:0,videoId:'seedvideo00'}}}};
 const p={getVideoData:()=>({video_id:'seedvideo00'})};
 const ctx={location:{origin:'https://music.youtube.com'},document:{querySelector:q=>q==='#movie_player'?p:null,querySelectorAll:q=>q==='ytmusic-player-queue ytmusic-player-queue-item'?[seed]:[]}};
 try { await vm.runInNewContext(expression,ctx); return 'accepted'; } catch (_) { return 'rejected'; }
}
(async()=>console.log(JSON.stringify([await attempt([]),await attempt([candidate('nextsong000'),candidate('alternate00')])])) )();
'''
    run = subprocess.run([shutil.which("node"), "-e", script, next_expression()],
                         text=True, capture_output=True, check=True)
    assert json.loads(run.stdout) == ["rejected", "rejected"]


def test_generated_js_fails_closed_without_ytm_facade():
    node = shutil.which("node")
    assert node
    script = "const vm=require('vm');try{vm.runInNewContext(process.argv[1],{location:{origin:'https://music.youtube.com'},document:{querySelector:()=>null}});process.exit(1)}catch(_){process.exit(0)}"
    assert subprocess.run([node, "-e", script, constant("STATE")]).returncode == 0


def test_cast_output_never_falls_back_to_tablet_when_receiver_is_unknown():
    script = r'''
const vm=require('vm'), expression=process.argv[1];
const p={getPlayerState:()=>1,getCurrentTime:()=>5,getVolume:()=>31,
 getVideoData:()=>({title:'Remote',author:'Artist'})};
const ctx={location:{origin:'https://music.youtube.com'},document:{querySelector:()=>p}};
let results=[];
for (const casting of [true,false,undefined]) {
 p.getOption=(a,b)=>b==='casting'?casting:null;
 try {results.push(vm.runInNewContext(expression,ctx).split('\t')[5]);}
 catch (_) {results.push('unavailable');}
}
delete p.getOption;
try {vm.runInNewContext(expression,ctx);results.push('unsafe');}
catch (_) {results.push('unavailable');}
console.log(JSON.stringify(results));
'''
    run = subprocess.run([shutil.which("node"), "-e", script, constant("STATE")],
                         text=True, capture_output=True, check=True)
    assert json.loads(run.stdout) == ["CAST SPEAKERS", "THIS TABLET", "unavailable", "unavailable"]


def test_state_classifies_visible_player_errors_and_selection():
    script = r'''
const vm=require('vm'), expression=process.argv[1];
function state({playerState=1,data={title:'Song',video_id:'abc'},error,visible=true}) {
 const p={getPlayerState:()=>playerState,getCurrentTime:()=>1,getVolume:()=>20,getVideoData:()=>data,getOption:()=>false};
 const node=error?{textContent:error,offsetParent:visible?{}:null}:null;
 const ctx={location:{origin:'https://music.youtube.com'},document:{querySelector:q=>q==='#movie_player'?p:null,querySelectorAll:()=>node?[node]:[]}};
 return vm.runInNewContext(expression,ctx).split('\t').at(6);
}
console.log(JSON.stringify([
 state({error:'Playback paused because there are too many devices streaming on your plan right now.'}),
 state({error:'Playback paused because there are too many devices streaming on your plan right now.',visible:false}),
 state({playerState:3}), state({data:{title:'',video_id:''}}), state({error:'The player encountered a problem'})
]));
'''
    run = subprocess.run([shutil.which("node"), "-e", script, constant("STATE")],
                         text=True, capture_output=True, check=True)
    assert json.loads(run.stdout) == ["STREAM_LIMIT", "READY", "BUFFERING", "CHOOSE", "PLAYER_ERROR"]


def test_empty_bootstrap_retry_preserves_live_music_and_sign_in():
    script = r'''
const vm=require('vm'), expression=process.argv[1];
const cases=[{}, {app:true}, {path:'/search'}, {ready:'loading'},
 {origin:'https://accounts.google.com'}, {tags:['FORM']}, {body:false}];
const out=cases.map(c=>{let scheduled=0,reloaded=0;
 const ctx={location:{origin:c.origin||'https://music.youtube.com',pathname:c.path||'/',reload:()=>reloaded++},
 document:{readyState:c.ready||'complete',body:c.body===false?null:{children:(c.tags||['NOSCRIPT','SCRIPT']).map(tagName=>({tagName}))},querySelector:()=>c.app?{}:null},
 setTimeout:fn=>{scheduled++;fn()}};
 return {result:vm.runInNewContext(expression,ctx),scheduled,reloaded};});
console.log(JSON.stringify(out));
'''
    run = subprocess.run([shutil.which("node"), "-e", script, constant("RECOVER_EMPTY")],
                         text=True, capture_output=True, check=True, timeout=5)
    result = json.loads(run.stdout)
    assert result[0] == {"result": "retry", "scheduled": 1, "reloaded": 1}
    assert all(r == {"result": "leave", "scheduled": 0, "reloaded": 0} for r in result[1:])


def test_stalled_player_page_transition_finishes_once_after_two_seconds():
    script = r'''
const vm=require('vm'), expression=process.argv[1];
let now=0, finished=0;
const animation={pending:true,playState:'running',playbackRate:1,currentTime:0,startTime:null,
 effect:{target:null,getTiming:()=>({duration:300,iterations:1}),getComputedTiming:()=>({endTime:300})},
 finish:()=>finished++};
const page={getAttribute:n=>n==='player-ui-state'?'PLAYER_BAR_ONLY':null,getAnimations:()=>[animation]};
animation.effect.target=page;
const ctx={location:{origin:'https://music.youtube.com'},document:{querySelector:()=>page},
 performance:{now:()=>now},Symbol,WeakMap};
const run=()=>vm.runInNewContext(expression,ctx);
console.log(JSON.stringify([run(),(now=1999,run()),(now=2000,run()),(now=4000,run()),finished]));
'''
    run = subprocess.run([shutil.which("node"), "-e", script,
                          constant("RECOVER_STALLED_PLAYER_UI")],
                         text=True, capture_output=True, check=True)
    assert json.loads(run.stdout) == ["waiting", "waiting", "finished", "waiting", 1]


def test_stalled_player_page_transition_clears_candidate_when_progressing():
    script = r'''
const vm=require('vm'), expression=process.argv[1];
let now=0, finished=0;
const animation={pending:true,playState:'running',playbackRate:1,currentTime:0,startTime:null,
 effect:{target:null,getTiming:()=>({duration:300,iterations:1}),getComputedTiming:()=>({endTime:300})},
 finish:()=>finished++};
const page={getAttribute:()=> 'PLAYER_PAGE_OPEN',getAnimations:()=>[animation]}; animation.effect.target=page;
const ctx={location:{origin:'https://music.youtube.com'},document:{querySelector:()=>page},performance:{now:()=>now},Symbol,WeakMap};
const run=()=>vm.runInNewContext(expression,ctx);
run(); now=2500; animation.currentTime=1; run(); now=4000; run();
console.log(finished);
'''
    run = subprocess.run([shutil.which("node"), "-e", script,
                          constant("RECOVER_STALLED_PLAYER_UI")],
                         text=True, capture_output=True, check=True)
    assert run.stdout.strip() == "0"


def test_stalled_player_page_transition_fails_closed_for_other_pages_and_finish_errors():
    script = r'''
const vm=require('vm'), expression=process.argv[1];
let now=0, calls=0;
const animation={pending:true,playState:'running',playbackRate:1,currentTime:0,startTime:null,
 effect:{target:null,getTiming:()=>({duration:300,iterations:1}),getComputedTiming:()=>({endTime:300})},
 finish:()=>{calls++;throw Error('site failure')}};
const page={getAttribute:()=> 'UNKNOWN',getAnimations:()=>[animation]}; animation.effect.target=page;
const ctx={location:{origin:'https://music.youtube.com'},document:{querySelector:()=>page},performance:{now:()=>now},Symbol,WeakMap};
const run=()=>vm.runInNewContext(expression,ctx);
const unknown=run(); page.getAttribute=()=> 'PLAYER_BAR_ONLY'; run(); now=2000; const failure=run(); now=4000; run();
ctx.location.origin='https://example.invalid'; const origin=run();
console.log(JSON.stringify([unknown,failure,origin,calls]));
'''
    run = subprocess.run([shutil.which("node"), "-e", script,
                          constant("RECOVER_STALLED_PLAYER_UI")],
                         text=True, capture_output=True, check=True)
    assert json.loads(run.stdout) == ["leave", "finish-error", "leave", 1]


def test_reused_player_animation_requires_a_fresh_stall_window():
    script = r'''
const vm=require('vm'), expression=process.argv[1];
const scenarios=['ui','effect','duration','iterations','end','rate','start'];
const outcomes=scenarios.map(change=>{
 let now=0, finished=0, ui='PLAYER_BAR_ONLY', duration=300, iterations=1, end=300;
 const page={getAttribute:()=>ui,getAnimations:()=>[animation]};
 const makeEffect=()=>({target:page,getTiming:()=>({duration,iterations}),getComputedTiming:()=>({endTime:end})});
 const animation={pending:true,playState:'running',playbackRate:1,currentTime:0,startTime:null,effect:makeEffect(),finish:()=>finished++};
 const ctx={location:{origin:'https://music.youtube.com'},document:{querySelector:()=>page},performance:{now:()=>now},Symbol,WeakMap};
 const run=()=>vm.runInNewContext(expression,ctx);
 run();now=2000;
 if(change==='ui')ui='PLAYER_PAGE_OPEN';
 if(change==='effect')animation.effect=makeEffect();
 if(change==='duration')duration=400;
 if(change==='iterations')iterations=Infinity;
 if(change==='end')end=400;
 if(change==='rate')animation.playbackRate=2;
 if(change==='start')animation.startTime=123;
 run();const early=finished;now=3999;run();const beforeDeadline=finished;now=4000;run();
 return [change,early,beforeDeadline,finished];
});console.log(JSON.stringify(outcomes));
'''
    run = subprocess.run([shutil.which("node"), "-e", script,
                          constant("RECOVER_STALLED_PLAYER_UI")],
                         text=True, capture_output=True, check=True)
    for change, early, before_deadline, finished in json.loads(run.stdout):
        assert early == before_deadline == 0, change
        assert finished == (0 if change in {"iterations", "start"} else 1), change
