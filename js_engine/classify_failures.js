'use strict';
// Classify each failing replay's FIRST illegal click as likely (B) client-also-fails
// (recording provably unreplayable in a faithful engine) vs (A) possible-our-bug.
// Signals for (B): inst-click on an instId >= nextInstId (unit not created yet), or a
// target-mode click whose target is the active player's OWN unit (illegal self chill/snipe),
// or a target/inst id that is absent AND >= nextInstId.
// Usage: node classify_failures.js <failuresJson> [replaysDir]
const fs = require('fs'); const path = require('path'); const zlib = require('zlib');
const C = require('./C'); const Analyzer = require('./Analyzer');
function loadReplay(fp){const raw=fs.readFileSync(fp);return fp.endsWith('.gz')?JSON.parse(zlib.gunzipSync(raw).toString('utf-8')):JSON.parse(raw.toString('utf-8'));}
function buildInitInfo(r){return{laneInfo:[{initResources:r.initInfo.initResources,base:r.deckInfo.base,randomizer:r.deckInfo.randomizer,initCards:r.initInfo.initCards}],mergedDeck:r.deckInfo.mergedDeck,scriptInfo:{whiteStarts:true},objectiveInfo:null,commandInfo:{commandList:r.commandInfo.commandList,clicksPerTurn:r.commandInfo.clicksPerTurn,gamePosition:r.commandInfo.commandList.length}};}
function findFile(dir,code){const enc=code.replace(/\+/g,'%2B').replace(/@/g,'%40');let fp=path.join(dir,enc+'.json.gz');if(!fs.existsSync(fp))fp=path.join(dir,code+'.json.gz');return fs.existsSync(fp)?fp:null;}

const failJson = process.argv[2] || 'C:/libraries/PrismataAI/docs/scratch/corpus_failures4.json';
const REPLAYS = process.argv[3] || 'C:/libraries/prismata-replay-parser/replays_archive';
const codes = JSON.parse(fs.readFileSync(failJson,'utf-8')).failures.map(f=>f.code);

function classifyOne(code){
  const fp = findFile(REPLAYS, code); if(!fp) return {code, cls:'NOFILE'};
  const replay = loadReplay(fp);
  const analyzer = new Analyzer(buildInitInfo(replay), -1, -1, null);
  const ctrl = analyzer.controller;
  const orig = analyzer.recordClick.bind(analyzer);
  let res = null;
  analyzer.recordClick = function(u,d,type,id,params){
    const gsBefore = ctrl.state;
    const inT = ctrl.inTargetMode, inS = ctrl.inSwipe;
    const nextId = gsBefore.nextInstId, glass = gsBefore.glassBroken, turn = gsBefore.turn, phase = gsBefore.phase;
    const r = orig(u,d,type,id,params);
    if(!res && r && r.canClick === false){
      let detail='';
      if(type===C.CLICK_INST || type===C.CLICK_INST_SHIFT){
        const inst = gsBefore.instIdToInst(id);
        const future = (id >= nextId);
        if(inst==null && future) detail='FUTURE-ID(absent, id>=nextInstId)';
        else if(inst==null) detail='ABSENT-ID(id<nextInstId, gone/never)';
        else if(inT && inst.owner===turn) detail='SELF-TARGET(target-mode, own unit)';
        else if(inst.owner===turn) detail=`OWN-UNIT(role=${inst.role})`;
        else detail=`ENEMY-UNIT(role=${inst.role})`;
      } else {
        detail = String(type);
      }
      res = {code, phase: phase===C.PHASE_ACTION?'ACT':phase===C.PHASE_DEFENSE?'DEF':'CONF',
             type:String(type), inT, inS, glass, nextId, detail};
    }
    return r;
  };
  try{ analyzer.loaderInit(); }catch(e){ if(!res) res={code,cls:'THREW:'+e.message}; }
  return res || {code, cls:'NO-ILLEGAL?'};
}

const rows = codes.map(classifyOne);
// bucket
const bucket = {};
for(const r of rows){
  const key = r.detail || r.cls || '?';
  (bucket[key]=bucket[key]||[]).push(r.code);
}
console.log('==== FIRST-ILLEGAL CLASSIFICATION (%d failing) ====', rows.length);
Object.entries(bucket).sort((a,b)=>b[1].length-a[1].length).forEach(([k,cs])=>{
  console.log(`\n[${cs.length}] ${k}`);
  console.log('   ' + cs.join(' '));
});
