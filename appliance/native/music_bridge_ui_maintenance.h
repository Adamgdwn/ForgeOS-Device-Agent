#ifndef FORGE_MUSIC_BRIDGE_UI_MAINTENANCE_H
#define FORGE_MUSIC_BRIDGE_UI_MAINTENANCE_H

/* This intentionally finishes only a proven-stalled, short player-page
 * transition.  Its WeakMap is page-local and vanishes with the document. */
static const char RECOVER_STALLED_PLAYER_UI[] =
    "(()=>{if(location.origin!=='https://music.youtube.com')return 'leave';const page="
    "document.querySelector('ytmusic-player-page'),ui=page?.getAttribute('player-ui-state');"
    "if(!page||(ui!=='PLAYER_BAR_ONLY'&&ui!=='PLAYER_PAGE_OPEN')||typeof page.getAnimations!=="
    "'function'||typeof performance?.now!=='function')return 'leave';const key=Symbol.for"
    "('forge.music.bridge.stalled-player-ui.v1'),cache=globalThis[key]instanceof WeakMap?"
    "globalThis[key]:(globalThis[key]=new WeakMap),now=performance.now();for(const animation of "
    "page.getAnimations()){const effect=animation.effect,timing=effect?.getTiming?.(),computed="
    "effect?.getComputedTiming?.(),duration=Number(timing?.duration),end=Number(computed?.endTime);"
    "if(effect?.target!==page||animation.pending!==true||animation.playState!=='running'||animation.startTime!==null||!Number.isFinite(animation.playbackRate)||"
    "animation.playbackRate<=0||!Number.isFinite(duration)||duration<=0||duration>1000||"
    "Number(timing?.iterations)!==1||!Number.isFinite(end)||end<=0||end>1000){cache.delete(animation);"
    "continue}const current=Number(animation.currentTime);if(!Number.isFinite(current)){cache.delete"
    "(animation);continue}const signature=JSON.stringify([ui,duration,timing.iterations,end,animation.playbackRate,animation.startTime]),prior=cache.get(animation);"
    "if(!prior||prior.current!==current||prior.effect!==effect||prior.signature!==signature){cache.set"
    "(animation,{current,effect,signature,seen:now});continue}if(now-prior.seen<2000||prior.attempted)continue;prior."
    "attempted=true;try{animation.finish();return 'finished'}catch(_){return 'finish-error'}}return "
    "'waiting'})()";

#endif
