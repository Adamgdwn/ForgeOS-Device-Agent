import test from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,rmSync} from "node:fs";
import {resolve} from "node:path";
import {tmpdir} from "node:os";
const root=mkdtempSync(resolve(tmpdir(),"galaxy-doc-tools-"));
process.env.GALAXY_STATE_DIR=resolve(root,"state");
const {Store}=await import("../server/store.ts");
const {WorkspaceTools}=await import("../server/workspace-tools.ts");
const {ensureTabletWorkspace}=await import("../server/tablet.ts");
test("On-device document tools preserve originals, save actual reports and reject stale or stopped writes",async()=>{
  const source=resolve(root,"source");mkdirSync(source);writeFileSync(resolve(source,"Notes.md"),"Original budget: 100\n");
  const store=new Store(":memory:");const p=store.addProject({name:"Meeting",path:source,kind:"local",description:""}),c=store.createConversation(p.id),tools=new WorkspaceTools(store);
  try{
    await assert.rejects(tools.tool(c.id,"workspace_read",{path:"../outside"}),/path|outside|relative/i);
    await assert.rejects(tools.tool(c.id,"workspace_write_draft",{path:"Notes.md",text:"Replace",expectedHash:""}),/isolated draft/);
    await assert.rejects(tools.tool(c.id,"workspace_prepare_report",{},()=>true,false),/read-only/);
    const prepared:any=await tools.tool(c.id,"workspace_prepare_report",{});
    const saved:any=await tools.tool(c.id,"workspace_save_report",{text:"# Brief\n\nBudget: 100.",expectedHash:prepared.hash});
    assert.equal(saved.text,"# Brief\n\nBudget: 100.");
    await assert.rejects(tools.tool(c.id,"workspace_save_report",{text:"Stale",expectedHash:prepared.hash}),/changed/);
    const read:any=await tools.tool(c.id,"workspace_read",{path:"Notes.md"});
    await assert.rejects(tools.tool(c.id,"workspace_write_draft",{path:"Notes.md",text:"Stopped",expectedHash:read.hash},()=>false),/stopped/);
    await tools.tool(c.id,"workspace_write_draft",{path:"Notes.md",text:"Proposed budget: 120\n",expectedHash:read.hash});
    assert.equal(readFileSync(resolve(source,"Notes.md"),"utf8"),"Original budget: 100\n");
    assert.equal(readFileSync(resolve(store.conversation(c.id).workspace,"Notes.md"),"utf8"),"Proposed budget: 120\n");
    for(const path of ["../outside.md",".env","Sources/credentials.json","note.sh"])
      await assert.rejects(tools.tool(c.id,"workspace_write_draft",{path,text:"Do not write",expectedHash:""}));
    const system=store.createConversation(ensureTabletWorkspace(store).id);
    await assert.rejects(tools.tool(system.id,"workspace_files",{}),/tools for this workspace/);
    await assert.rejects(tools.tool(c.id,"run_shell",{}),/Unsupported/);
  }finally{store.close();rmSync(root,{recursive:true,force:true});}
});
