"""Execute the guarded YTM queue-rendering installer against a fake Polymer DOM."""
import json
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]
HEADER = (ROOT / "appliance/native/music_bridge_queue_maintenance.h").read_text()


def installer():
    match = re.search(r"static const char MAINTAIN_MUSIC_QUEUE_RENDERING\[\] =\s*((?:\"(?:\\.|[^\"\\])*\"\s*)+);", HEADER, re.S)
    assert match
    return "".join(json.loads(token) for token in re.findall(r'"(?:\\.|[^"\\])*"', match.group(1)))


def run(script):
    node = shutil.which("node")
    assert node, "node is required for queue JavaScript behavior tests"
    completed = subprocess.run([node, "-e", script, installer()], text=True,
                               capture_output=True, check=True, timeout=5)
    return json.loads(completed.stdout)


def test_queue_prefixes_eventually_render_all_rows_in_order_without_mutating_data():
    result = run(r'''
const vm=require('vm'), expression=process.argv[1], timers=[];
const data=Array.from({length:20},(_,i)=>({id:i})), original=data.slice(), writes=[];
const c={selectedQueueItemIndex:15,computeShowItemsToRender:a=>a,setProperties:(v)=>writes.push(v.itemsToRender)};
const q={inst:c,polymerController:c,isConnected:true,data};
const document={querySelector:s=>s==='ytmusic-player-queue'?q:null};
const ctx={location:{origin:'https://music.youtube.com'},document,Symbol,setTimeout:f=>(timers.push(f),timers.length),clearTimeout:()=>{}};
vm.runInNewContext(expression,ctx); const first=c.computeShowItemsToRender(data); while(timers.length)timers.shift()();
console.log(JSON.stringify({first:first.map(x=>x.id),writes:writes.map(x=>x.map(y=>y.id)),data:data.map(x=>x.id),same:data.every((x,i)=>x===original[i])}));
''')
    assert result["first"] == list(range(18))
    assert result["writes"][-1] == list(range(20))
    assert result["data"] == list(range(20)) and result["same"]


def test_queue_installer_is_idempotent_and_unchanged_input_does_not_restart_work():
    result = run(r'''
const vm=require('vm'), expression=process.argv[1], timers=[]; const data=Array.from({length:30},(_,i)=>i);
let originalCalls=0;const original=a=>{originalCalls++;return a};const c={selectedQueueItemIndex:0,computeShowItemsToRender:original,setProperties:()=>{}};
const q={inst:c,polymerController:c,isConnected:true,data};const ctx={location:{origin:'https://music.youtube.com'},document:{querySelector:()=>q},Symbol,setTimeout:f=>(timers.push(f),timers.length),clearTimeout:()=>{}};
const a=vm.runInNewContext(expression,ctx), wrapped=c.computeShowItemsToRender;const b=vm.runInNewContext(expression,ctx);wrapped(data);wrapped(data);
console.log(JSON.stringify({a,b,same:wrapped===c.computeShowItemsToRender,timers:timers.length,originalCalls}));
''')
    assert result == {"a": "installed", "b": "installed", "same": True, "timers": 1, "originalCalls": 2}


def test_queue_replacement_cancels_old_work_and_installs_on_new_component():
    result = run(r'''
const vm=require('vm'), expression=process.argv[1], timers=[];let q;
const make=()=>{const data=Array.from({length:20},(_,i)=>i), original=a=>a, c={selectedQueueItemIndex:0,computeShowItemsToRender:original,setProperties:()=>{}};return {inst:c,polymerController:c,isConnected:true,data,original}};
const old=make();q=old;const ctx={location:{origin:'https://music.youtube.com'},document:{querySelector:()=>q},Symbol,setTimeout:f=>(timers.push(f),timers.length),clearTimeout:()=>{}};
vm.runInNewContext(expression,ctx);old.inst.computeShowItemsToRender(old.data);const fresh=make();q=fresh;vm.runInNewContext(expression,ctx);timers.shift()();
console.log(JSON.stringify({oldRestored:old.inst.computeShowItemsToRender===old.original,newInstalled:fresh.inst.computeShowItemsToRender!==fresh.original}));
''')
    assert result == {"oldRestored": True, "newInstalled": True}


def test_queue_new_data_cancels_stale_generation_and_disconnect_stops_safely():
    result = run(r'''
const vm=require('vm'), expression=process.argv[1], timers=[], writes=[];let data=Array.from({length:20},(_,i)=>'old'+i);
const original=a=>a;const c={selectedQueueItemIndex:0,computeShowItemsToRender:original,setProperties:v=>writes.push(v.itemsToRender[0])};
const q={inst:c,polymerController:c,isConnected:true,get data(){return data}};
const ctx={location:{origin:'https://music.youtube.com'},document:{querySelector:()=>q},Symbol,setTimeout:f=>(timers.push(f),timers.length),clearTimeout:()=>{}};
vm.runInNewContext(expression,ctx);c.computeShowItemsToRender(data);data=Array.from({length:20},(_,i)=>'new'+i);c.computeShowItemsToRender(data);
timers.shift()(); q.isConnected=false;timers.shift()();
console.log(JSON.stringify({writes,restored:c.computeShowItemsToRender===original}));
''')
    # The stale old callback writes nothing; the new callback alone may write,
    # and a disconnected queue is stopped without any further mutation.
    assert result == {"writes": [], "restored": True}


def test_queue_fails_closed_for_unsupported_or_oversized_data_and_restores_on_exception():
    result = run(r'''
const vm=require('vm'), expression=process.argv[1], timers=[];const data=Array.from({length:4},(_,i)=>i);let calls=0;
const original=a=>{calls++;return a};const c={selectedQueueItemIndex:0,computeShowItemsToRender:original,setProperties:()=>{throw Error('bad Polymer')}};
const q={inst:c,polymerController:c,isConnected:true,data};const ctx={location:{origin:'https://music.youtube.com'},document:{querySelector:()=>q},Symbol,setTimeout:f=>(timers.push(f),timers.length),clearTimeout:()=>{}};
vm.runInNewContext(expression,ctx);const nonarray=c.computeShowItemsToRender('no');const huge=Array.from({length:1001},(_,i)=>i);const oversize=c.computeShowItemsToRender(huge);q.data=Array.from({length:20},(_,i)=>i);c.computeShowItemsToRender(q.data);timers.shift()();
console.log(JSON.stringify({nonarray,oversize:oversize.length,calls,restored:c.computeShowItemsToRender===original}));
''')
    assert result == {"nonarray": "no", "oversize": 1001, "calls": 4, "restored": True}


def test_stale_callback_cannot_uninstall_or_cancel_a_new_generation():
    result = run(r'''
const vm=require('vm'), timers=[], writes=[], original=a=>a;
const c={selectedQueueItemIndex:0,computeShowItemsToRender:original,setProperties:v=>writes.push(v.itemsToRender)};
const q={inst:c,polymerController:c,isConnected:true,data:Array(16).fill('old')};
const ctx={location:{origin:'https://music.youtube.com'},document:{querySelector:()=>q},Symbol,setTimeout:f=>(timers.push(f),timers.length+1),clearTimeout:()=>{}};
vm.runInNewContext(process.argv[1],ctx);c.computeShowItemsToRender(q.data);
q.data=Array(16).fill('new');c.computeShowItemsToRender(q.data);
while(timers.length)timers.shift()();
console.log(JSON.stringify({installed:c.computeShowItemsToRender!==original,onlyNew:writes.every(a=>a.every(x=>x==='new')),last:writes.at(-1).length}));
''')
    assert result == {"installed": True, "onlyNew": True, "last": 16}


def test_canonical_data_change_without_compute_prevents_stale_write():
    result = run(r'''
const vm=require('vm'), timers=[], writes=[];
const c={selectedQueueItemIndex:0,computeShowItemsToRender:a=>a,setProperties:v=>writes.push(v.itemsToRender)};
const q={inst:c,polymerController:c,isConnected:true,data:Array(20).fill('old')};
const ctx={location:{origin:'https://music.youtube.com'},document:{querySelector:()=>q},Symbol,setTimeout:f=>(timers.push(f),timers.length+1),clearTimeout:()=>{}};
vm.runInNewContext(process.argv[1],ctx);c.computeShowItemsToRender(q.data);q.data=Array(20).fill('new');timers.shift()();
console.log(JSON.stringify({writes:writes.length}));
''')
    assert result == {"writes": 0}


def test_batch_exception_restores_full_rendering_and_disables_reinstallation():
    result = run(r'''
const vm=require('vm'), timers=[], original=a=>a;let writes=0,last;
const c={selectedQueueItemIndex:0,computeShowItemsToRender:original,setProperties:v=>{if(++writes===1)throw Error('transient');last=v.itemsToRender}};
const q={inst:c,polymerController:c,isConnected:true,data:Array(20).fill('track')};
const ctx={location:{origin:'https://music.youtube.com'},document:{querySelector:()=>q},Symbol,setTimeout:f=>(timers.push(f),timers.length+1),clearTimeout:()=>{}};
vm.runInNewContext(process.argv[1],ctx);c.computeShowItemsToRender(q.data);timers.shift()();
const retry=vm.runInNewContext(process.argv[1],ctx);
console.log(JSON.stringify({retry,restored:c.computeShowItemsToRender===original,full:last===q.data}));
''')
    assert result == {"retry": "disabled", "restored": True, "full": True}


def test_original_filtered_render_list_is_preserved_and_wrong_origin_is_untouched():
    result = run(r'''
const vm=require('vm'), timers=[], filtered=['original'], original=()=>filtered;
const c={selectedQueueItemIndex:0,computeShowItemsToRender:original,setProperties:()=>{throw Error('write')}};
const q={inst:c,polymerController:c,isConnected:true,data:Array(20).fill('track')};
const ctx={location:{origin:'https://accounts.google.com'},document:{querySelector:()=>q},Symbol,setTimeout:f=>(timers.push(f),timers.length+1),clearTimeout:()=>{}};
const wrong=vm.runInNewContext(process.argv[1],ctx),untouched=c.computeShowItemsToRender===original;
ctx.location.origin='https://music.youtube.com';vm.runInNewContext(process.argv[1],ctx);
console.log(JSON.stringify({wrong,untouched,same:c.computeShowItemsToRender(q.data)===filtered,timers:timers.length}));
''')
    assert result == {"wrong": "leave", "untouched": True, "same": True, "timers": 0}


def test_foreign_override_stops_our_writes_and_throwing_data_getter_is_contained():
    result = run(r'''
const vm=require('vm');
function attempt(foreign){const timers=[],writes=[],data=Array(20).fill('track');let bad=false;
 const original=a=>a,other=a=>a,c={selectedQueueItemIndex:0,computeShowItemsToRender:original,setProperties:v=>writes.push(v.itemsToRender.length)};
 const q={inst:c,polymerController:c,isConnected:true,get data(){if(bad)throw Error('data getter');return data}};
 const ctx={location:{origin:'https://music.youtube.com'},document:{querySelector:()=>q},Symbol,setTimeout:f=>(timers.push(f),timers.length),clearTimeout:()=>{}};
 vm.runInNewContext(process.argv[1],ctx);c.computeShowItemsToRender(data);
 if(foreign)c.computeShowItemsToRender=other;else bad=true;
 let error='';try{timers.shift()()}catch(e){error=e.message}
 return {error,writes,restored:c.computeShowItemsToRender===(foreign?other:original),retry:vm.runInNewContext(process.argv[1],ctx)};
}
console.log(JSON.stringify([attempt(true),attempt(false)]));
''')
    assert result == [{"error": "", "writes": [], "restored": True, "retry": "disabled"}] * 2
