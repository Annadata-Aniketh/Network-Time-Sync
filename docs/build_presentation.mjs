// Run from the repository root with the bundled Artifact Tool and PRESENTATION_SKILL_DIR.
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const root = process.cwd();
const entry = process.env.ARTIFACT_TOOL_ENTRY ?? '@oai/artifact-tool';
const { Presentation, PresentationFile } = await import(entry);
const skill = process.env.PRESENTATION_SKILL_DIR;
const python = process.env.PRESENTATION_PYTHON;
if (!skill || !python) throw new Error('Set PRESENTATION_SKILL_DIR and PRESENTATION_PYTHON');
const build = path.join(root, 'tmp/deck');
await fs.mkdir(build, {recursive:true});
const evidence = JSON.parse(await fs.readFile(path.join(root, 'docs/results/audit.json'), 'utf8'));
const presentation = Presentation.create({slideSize:{width:1280,height:720}});
const C = {ink:'#14283B',sub:'#40566A',green:'#087F70',red:'#AD4D44',paper:'#F7F9FA',line:'#D5DFE5'};
function shape(s,x,y,w,h,fill,geometry='rect') {
  return s.shapes.add({geometry,position:{left:x,top:y,width:w,height:h},fill,
    line:{fill:'none',width:0,style:'solid'}});
}
function text(s,str,x,y,w,h,size=26,color=C.ink,bold=false) {
  const a=shape(s,x,y,w,h,'none','textbox');a.text=str;
  a.text.style={typeface:'Arial',fontSize:size,color,bold};return a;
}
function slide(title,notes='') {
  const s=presentation.slides.add();s.background.fill=C.paper;
  shape(s,60,48,8,52,C.green);text(s,title,86,46,1130,78,42,C.ink,true);
  text(s,String(presentation.slides.items.length).padStart(2,'0'),1160,660,60,30,18,C.sub);
  s.speakerNotes.text=notes;return s;
}
function para(s,heading,body,x,y,w=510) {
  text(s,heading,x,y,w,52,29,C.green,true);text(s,body,x,y+60,w,210,26,C.ink);
}
function table(s,values,x,y,w,h,columns) {
  const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,values,columnWidths:columns});
  t.borders.assign({style:'solid',fill:C.line,width:1});
  for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){
    const cell=t.getCell(r,c);cell.fill=r===0?C.ink:(r%2?'#FFFFFF':C.paper);
    cell.text.style={typeface:'Arial',fontSize:23,color:r===0?'#FFFFFF':C.ink,bold:r===0};
  }
  return t;
}
const source='Source: docs/evidence/vm-results-20261101-195256.tar.gz. Audit: docs/results/audit.json. All measurements are from the supplied Linux VM.';
{
 const s=slide('Network Time Synchronization',source+' Five comparisons, 60 seconds per mode; one separate recovery test. Virtual clocks only.');
 text(s,'UDP clock correction over an SDN network',86,160,1080,70,36,C.sub);
 text(s,'1.03–1.16 ms',86,285,1080,100,76,C.green,true);
 text(s,'Optimized mean clock error across five VM runs',90,390,1070,55,30);
 text(s,'Five comparisons · automatic rerouting · recovery verified',90,510,1100,65,28,C.sub);
 text(s,'Team 11  |  VM measurements: 1 November 2026',90,590,1100,42,24,C.sub);
}
{
 const s=slide('Network architecture',source+' topology/custom_topo.py fixes the host MACs, switch ports and link parameters. OS-Ken uses OpenFlow 1.3 over TCP 6653. The application and background load use UDP.');
 const box=(label,x,y,w=130,h=65)=>{shape(s,x,y,w,h,C.ink);text(s,label,x+14,y+15,w-24,h-12,24,'#FFFFFF',true);};
 // Orthogonal links, drawn before their endpoint boxes.
 for(const [x,y,w,h] of [[265,315,155,3],[550,315,45,3],[592,220,3,210],[595,220,85,3],[595,427,85,3],[810,220,85,3],[810,427,85,3],[892,220,3,210],[895,315,55,3],[1080,315,130,3]])shape(s,x,y,w,h,C.green);
 box('Clients\n+ load',85,275,180,100);box('s1',420,285);box('s2',680,190);box('s3',680,397);box('s4',950,285);box('Server\n+ sink',1100,275,130,100);
 text(s,'Path A · 10 Mbps',615,140,330,42,25,C.sub);text(s,'Path B · 50 Mbps',615,485,330,42,25,C.sub);
 text(s,'Mininet hosts and links  /  Open vSwitch data plane  /  OS-Ken controller',85,575,1120,62,25);
}
{
 const s=slide('Four-timestamp UDP exchange',source+' app/protocol.py implements the 35-byte binary packet and formulas. Server uses a thread pool. Each benchmark client runs persistently inside its Mininet namespace.');
 table(s,[['Timestamp','Event','Clock'],['t0','Client sends','Client virtual'],['t1','Server receives','Reference'],['t2','Server replies','Reference'],['t3','Client receives','Client virtual']],85,155,1110,280,[180,470,460]);
 text(s,'RTT = (t3 − t0) − (t2 − t1)',90,475,1080,45,30,C.green,true);
 text(s,'Offset = ((t1 − t0) + (t2 − t3)) / 2',90,530,1080,45,30,C.green,true);
 text(s,'Add offset to virtual time. Unequal directional delays bias the estimate.',90,600,1080,44,24,C.sub);
}
{
 const s=slide('Prioritization and automatic path changes',source+' sdn/controller.py; sdn/flow_rules.json. Queue 1 reserves 2 Mbps for sync; queue 2 caps background traffic at 6 Mbps on edge Path A egress. Threshold is load, not delay.');
 para(s,'Classify','UDP 12300 → sync queue\nUDP 5001 → background queue',85,180);
 para(s,'Monitor','Poll s1 port 5 every 2 seconds.\nCalculate Mbps from byte counters.',680,180);
 shape(s,85,420,1110,2,C.line);
 text(s,'≥ 4 Mbps',85,465,450,65,48,C.green,true);text(s,'Move sync traffic to Path B',85,545,500,65,28);
 text(s,'3 low-load polls',680,465,520,65,44,C.green,true);text(s,'Remove reroute rules; return to Path A',680,545,510,75,28);
}
{
 const s=slide('Comparison schedule',source+' Clients begin 100 ms ahead with drift rates +20, -15, +30 ms/s; interval 0.5 s. The same offered load is used in both modes. QoS changes admitted background rate. This tests QoS and routing together.');
 table(s,[['Time','Condition'],['0–20 s','Normal: three clients synchronize'],['20–40 s','Add UDP load: iperf -b 12M'],['40–60 s','Keep load; add 50 ms delay and 15 ms jitter']],85,170,1110,265,[240,870]);
 text(s,'Baseline: Path A, ordinary forwarding',90,480,1100,50,30,C.red,true);
 text(s,'Optimized: application queues + automatic rerouting',90,540,1100,50,30,C.green,true);
 text(s,'Five completed comparisons; incomplete startup attempts excluded.',90,610,1100,35,24,C.sub);
}
{
 const s=slide('Measured clock error and round-trip delay',source+' Values are per-run means, recalculated from CSVs. RTT uses successful replies only. Error includes failed attempts and is sampled immediately after correction. These are five trials, not a claim of statistical significance.');
 const runs=[...new Set(evidence.trials.map(r=>r.run))];
 for(const [index,key,title] of [[0,'Mean Clock Error (ms)','Mean clock error (ms)'],[1,'Mean RTT (ms)','Mean RTT (ms)']]){
  const chart=s.charts.add('bar',{position:{left:70+index*610,top:160,width:565,height:390},title,titleTextStyle:{fontSize:26},
   categories:runs.map((r,i)=>'Run '+(i+1)),series:['baseline','optimized'].map((mode,i)=>({name:mode==='baseline'?'Baseline':'Optimized',values:runs.map(run=>Number(evidence.trials.find(r=>r.run===run&&r.mode===mode)[key].toFixed(3))),fill:i?C.green:C.red})),
   barOptions:{direction:'column',grouping:'clustered'},hasLegend:true,legend:{position:'bottom',textStyle:{fontSize:19}},
   xAxis:{textStyle:{fontSize:17}},yAxis:{numberFormatCode:'0',textStyle:{fontSize:17}},
   dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'0.0',textStyle:{fontSize:15}}});
 }
 text(s,'Optimized error: 1.034–1.158 ms   |   Optimized RTT: 21.959–22.892 ms',85,580,1120,65,27,C.green,true);
}
{
 const s=slide('Failure analysis',source+' docs/results/raw_review.md and audit.json. Every successful sequence is in the server log; none of the 393 baseline timeouts is. This supports pre-handling request loss but does not locate the exact drop point. Timeout waits can reduce the number of attempts.');
 table(s,[['Mode','Attempts','Success','Timeout','Invalid'],['Baseline','1,753','1,360','393','0'],['Optimized','1,800','1,800','0','0']],85,175,1110,210,[270,210,210,210,210]);
 text(s,'All baseline timeouts occurred under load.',90,440,1100,50,30,C.red,true);
 text(s,'No timed-out request appears in the server’s handled-request log.',90,505,1100,65,28);
 text(s,'Timeout counts are application observations, not packet-capture loss rates.',90,590,1100,60,24,C.sub);
}
{
 const s=slide('Automatic recovery verified',source+' Run 20261101-194117 was independently re-evaluated using its raw CSVs and flow dumps. There is no injected impairment in the recovery scenario. No manual flow restoration is performed.');
 text(s,'Normal → UDP load → load stopped',85,160,1110,65,36,C.sub);
 text(s,'108',85,285,470,90,70,C.green,true);text(s,'Sync requests carried on Path B',90,385,520,70,29);
 text(s,'132 → 204',680,285,520,90,62,C.green,true);text(s,'Path A sync counter after load stopped',685,385,510,90,29);
 shape(s,85,490,1110,2,C.line);
 text(s,'PASS: reroute rules removed from s1, s3, and s4',90,525,1100,46,29,C.green,true);
 text(s,'PASS: all three clients received replies during recovery',90,582,1100,46,29,C.green,true);
}
{
 const s=slide('What these measurements establish',source+' Limits are in docs/project_report.md. Convergence means three successive sample rounds below 2 ms for every client. It is not reroute time. Runtime versions recorded at export: Linux Mint 22.3, Python 3.12.3, Mininet 2.3.0, OVS 3.3.9, OS-Ken 2.11.2, Eventlet 0.40.4.');
 para(s,'Observed','Lower RTT and clock error under load.\nZero optimized failures in five runs.\nAutomatic rerouting and recovery.',85,180);
 para(s,'Measurement limits','Error sampled after correction.\nShared VM clock is the reference.\nQoS and rerouting tested together.',680,180);
 shape(s,85,465,1110,2,C.line);
 text(s,'Initial convergence varied; optimized mode was slower in two trials.',90,505,1100,75,28);
 text(s,'The experiment changes virtual clocks, not the machine’s system clock.',90,595,1100,44,24,C.sub);
}
{
 const s=slide('Live demonstration',source+' README.md documents installation and usage. Full raw results, audit outputs, archived screenshots, report, and source code are committed in the repository. Presentation generated from the same audit.json.');
 text(s,'sudo bash scripts/run_demo.sh',85,170,1110,65,38,C.green,true);
 const steps=[['1','Check environment'],['4','Run the baseline / optimized comparison'],['5, 6','Generate plots and inspect the summary'],['9','Run the separate automatic recovery test']];
 steps.forEach(([number,label],i)=>{text(s,number,90,285+i*70,135,50,30,C.green,true);text(s,label,250,285+i*70,935,52,30);});
 text(s,'Source evidence and reproducible audit: docs/results/ and docs/build_results.py',90,610,1100,42,23,C.sub);
}
const {finalizePresentation,applyPresentationChartFont}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
for(const s of presentation.slides.items) for(const chart of s.charts.items) applyPresentationChartFont(chart,{fontFamily:'Arial'});
for(const [i,s] of presentation.slides.items.entries()){
 const blob=await presentation.export({slide:s,format:'png',scale:1});
 await fs.writeFile(path.join(build,`slide-${i+1}.png`),new Uint8Array(await blob.arrayBuffer()));
}
const candidate=path.join(build,'candidate.pptx');
await (await PresentationFile.exportPptx(presentation)).save(candidate);
const output=path.resolve(process.env.PRESENTATION_OUTPUT ?? path.join(root,'docs/network-time-sync.pptx'));
const result=await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:output,
 pythonExecutable:python,integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],
 requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[6],materializeLiteralChartWorkbooks:true,
 fontPolicy:{basis:'design',families:['Arial']},verifyArtifactToolImport:true,
 receiptPath:path.join(build,'validation.json')});
console.log(JSON.stringify(result));
