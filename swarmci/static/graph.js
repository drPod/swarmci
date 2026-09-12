// Adapted from tiny-browser-agent graph-render.js, Apache-2.0.
// Modified for SwarmCI: screenshot cards, stable swarm layout, worker overlays,
// aggregated transitions and recorded-event animation. See vendor/NOTICE.md.
const atlas = (() => {
  const svgEl = document.getElementById('graph-svg');
  const wrapEl = document.getElementById('graph-wrap');
  const fitBtn = document.getElementById('graph-fit');
  const zoomInBtn = document.getElementById('graph-zoom-in');
  const zoomOutBtn = document.getElementById('graph-zoom-out');
  const svg = d3.select(svgEl);
  const root = svg.append('g').attr('class','graph-root');
  const pageG = root.append('g').attr('class','page-groups');
  const linkG = root.append('g'), nodeG = root.append('g'), agentG = root.append('g'), pulseG = root.append('g');
  let autoFit=true;
  const zoomBehavior = d3.zoom().scaleExtent([0.12,2.5]).on('zoom', event => {
    root.attr('transform',event.transform);
    if(event.sourceEvent)autoFit=false;
    svg.classed('zoomed-out', event.transform.k < .38);
  });
  svg.call(zoomBehavior);
  const simulation = d3.forceSimulation()
    .force('link',d3.forceLink().id(d=>d.id).distance(320).strength(.12))
    .force('charge',d3.forceManyBody().strength(-1200).distanceMax(700))
    .force('x',d3.forceX(d=>d._targetX).strength(.9))
    .force('y',d3.forceY(d=>d._targetY).strength(.9))
    .force('collide',d3.forceCollide(112).strength(1).iterations(3)).on('tick',ticked);
  let lastData=null,lastWorkers=[],pageGroups=[],collapsedPages=new Set();
  let nodesData=[],linksData=[],nodeSel=nodeG.selectAll('g'),linkSel=linkG.selectAll('path');
  let workers=[],focused=null,selectedPath=new Set(),initialFit=false,topology='';
  function graphNodeRadius(){return 160;}
  function resize(){
    const {width,height}=wrapEl.getBoundingClientRect();
    if(!width||!height)return;
    svgEl.setAttribute('viewBox',`${-width/2} ${-height/2} ${width} ${height}`);
    svgEl.setAttribute('width',width);svgEl.setAttribute('height',height);
  }
  new ResizeObserver(resize).observe(wrapEl);resize();
  function graphTransition() {
    return svg.transition().duration(220);
  }

  function zoomBy(factor) {
    autoFit=false;
    graphTransition().call(zoomBehavior.scaleBy, factor);
  }

  function fitToNodes() {
    if (!nodesData.length) {
      graphTransition().call(zoomBehavior.transform, d3.zoomIdentity);
      return;
    }
    const { width, height } = wrapEl.getBoundingClientRect();
    if (!width || !height) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    nodesData.forEach(n => {
      const x = Number.isFinite(n.x) ? n.x : n._targetX;
      const y = Number.isFinite(n.y) ? n.y : n._targetY;
      if (!Number.isFinite(x) || !Number.isFinite(y)) return;
      const r = graphNodeRadius(n) + 8;
      if (x - r < minX) minX = x - r;
      if (x + r > maxX) maxX = x + r;
      if (y - r < minY) minY = y - r;
      if (y + r > maxY) maxY = y + r;
    });
    if (!Number.isFinite(minX) || !Number.isFinite(minY)) {
      graphTransition().call(zoomBehavior.transform, d3.zoomIdentity);
      return;
    }
    const boundsWidth = Math.max(1, maxX - minX);
    const boundsHeight = Math.max(1, maxY - minY);
    const padding = 40;
    const scale = Math.max(
      0.12,
      Math.min(1.2, Math.min((width - padding) / boundsWidth, (height - padding) / boundsHeight))
    );
    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;
    const transform = d3.zoomIdentity
      .translate(-centerX * scale, -centerY * scale)
      .scale(scale);
    graphTransition().call(zoomBehavior.transform, transform);
  }

  if (fitBtn) fitBtn.addEventListener('click', (event) => { event.stopPropagation(); autoFit=true; fitToNodes(); });
  if (zoomInBtn) zoomInBtn.addEventListener('click', (event) => { event.stopPropagation(); zoomBy(1.25); });
  if (zoomOutBtn) zoomOutBtn.addEventListener('click', (event) => { event.stopPropagation(); zoomBy(0.8); });

  function drag() {
    return d3.drag()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x; d.fy = d.y;
      })
      .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y; })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0);
        if (d.isRoot) {
          if (d._rootPin) {
            d.fx = d._rootPin.x;
            d.fy = d._rootPin.y;
          } else {
            d.fx = null;
            d.fy = null;
          }
          return;
        }
        d.fx = null; d.fy = null;
      });
  }

  function edgePath(d){
    const a=d.source,b=d.target;
    if(a.id===b.id)return `M${a.x+60},${a.y-69} C${a.x+160},${a.y-160} ${a.x+205},${a.y+30} ${a.x+99},${a.y+5}`;
    const direction=b.x>=a.x?1:-1;
    const sx=a.x+direction*100,tx=b.x-direction*103;
    return `M${sx},${a.y} C${sx+direction*95},${a.y} ${tx-direction*95},${b.y} ${tx},${b.y}`;
  }
  function ticked(){
    pageG.selectAll('.page-group').each(function(group){
      const members=nodesData.filter(n=>n.page_key===group.id&&!n.isPage);if(!members.length)return;
      const x=d3.min(members,n=>n.x)-125,y=d3.min(members,n=>n.y)-147;
      const width=d3.max(members,n=>n.x)-x+125,height=d3.max(members,n=>n.y)-y+106;
      const g=d3.select(this);g.attr('transform',`translate(${x},${y})`);
      g.select('rect.page-boundary').attr('width',width).attr('height',height);
      g.select('.page-collapse').attr('transform',`translate(${width-86},24)`);
    });
    linkSel.attr('d',edgePath);
    nodeSel.attr('transform',d=>`translate(${d.x},${d.y})`);
    agentG.selectAll('.agent-marker').attr('transform',d=>{
      const n=nodesData.find(n=>n.id===d.state);return `translate(${n?.x||0},${(n?.y||0)-89-d.slot*23})`;
    });
  }
  function reset(){
    simulation.stop();autoFit=true;collapsedPages=new Set();pageGroups=[];pageG.selectAll('*').remove();nodesData=[];linksData=[];topology='';initialFit=false;workers=[];
    nodeG.selectAll('*').remove();linkG.selectAll('*').remove();agentG.selectAll('*').remove();pulseG.selectAll('*').interrupt().remove();
    svg.call(zoomBehavior.transform,d3.zoomIdentity);
  }
  function update(data,workerList=[]){
    lastData=data;lastWorkers=workerList;
    pageGroups=(data.page_groups||[]).filter(g=>data.nodes.some(n=>n.page_key===g.id)).map(g=>({...g,states:data.nodes.filter(n=>n.page_key===g.id).map(n=>n.id),arrivals:data.edges.filter(e=>data.nodes.find(n=>n.id===e.target)?.page_key===g.id).length}));
    const nodePages=new Map(data.nodes.map(n=>[n.id,n.page_key]));
    const endpoint=id=>collapsedPages.has(nodePages.get(id))?'page:'+nodePages.get(id):id;
    const visibleNodes=data.nodes.filter(n=>!collapsedPages.has(n.page_key));
    for(const group of pageGroups.filter(g=>collapsedPages.has(g.id))){
      const first=data.nodes.find(n=>n.page_key===group.id);visibleNodes.push({...first,id:'page:'+group.id,isPage:true,label:group.label,variant_note:`${group.states.length} state variants · ${group.arrivals} arrivals`,screenshot:first?.screenshot});
    }
    data={...data,nodes:visibleNodes,edges:data.edges.map(e=>({...e,source:endpoint(e.source),target:endpoint(e.target)})).filter(e=>!e.source.startsWith('page:')||e.source!==e.target)};
    workerList=workerList.map(w=>({...w,state:endpoint(w.state)}));
    const groupSel=pageG.selectAll('.page-group').data(pageGroups.filter(g=>!collapsedPages.has(g.id)),g=>g.id).join(enter=>{
      const g=enter.append('g').attr('class','page-group');
      g.append('rect').attr('class','page-boundary').attr('rx',17);
      g.append('text').attr('class','page-group-title').attr('x',23).attr('y',29).attr('tabindex',0).attr('role','button').on('click',(e,d)=>window.selectPage(d.id)).on('keydown',(e,d)=>{if(e.key==='Enter')window.selectPage(d.id);});
      g.append('text').attr('class','page-group-meta').attr('x',23).attr('y',49);
      const collapse=g.append('g').attr('class','page-collapse').attr('tabindex',0).attr('role','button').on('click',(e,d)=>toggleGroup(d.id)).on('keydown',(e,d)=>{if(e.key==='Enter')toggleGroup(d.id);});
      collapse.append('rect').attr('width',67).attr('height',23).attr('y',-12).attr('rx',5);
      collapse.append('text').attr('x',9).attr('y',3).text('Collapse −');return g;
    });
    groupSel.select('.page-group-title').text(g=>g.label.slice(0,46));
    groupSel.select('.page-group-meta').text(g=>`${g.states.length} STATE VARIANTS  ·  ${g.arrivals} ARRIVALS  ·  SAME PAGE`);
    const old=new Map(nodesData.map(n=>[n.id,n])),depths={};
    const bad=new Set(data.bugs.map(b=>b.state));
    const arrivals={};data.edges.forEach(e=>arrivals[e.target]=(arrivals[e.target]||0)+1);
    data.nodes.forEach(n=>(depths[n.depth]??=[]).push(n));
    const layouts=new Map();let pageX=0;
    for(const group of pageGroups){
      const members=data.nodes.filter(n=>n.page_key===group.id),ratio=Math.max(1,wrapEl.clientWidth/Math.max(1,wrapEl.clientHeight)),cols=Math.min(members.length,8,Math.ceil(Math.sqrt(members.length*ratio*.8)));
      members.forEach((n,i)=>layouts.set(n.id,{x:pageX+(i%cols)*295,y:Math.floor(i/cols)*245}));
      pageX+=Math.max(1,cols)*295+180;
    }
    nodesData=data.nodes.map((n,i)=>{
      const target=layouts.get(n.id)||{x:n.depth*310,y:i*200};
      return {...old.get(n.id),...n,_targetX:target.x,_targetY:target.y,x:old.get(n.id)?.x??target.x,y:old.get(n.id)?.y??target.y,bad:bad.has(n.id),arrivals:arrivals[n.id]||0};
    });
    const grouped=new Map();
    for(const e of data.edges){const key=e.source+'|'+e.target;let g=grouped.get(key);if(!g){g={id:key,source:e.source,target:e.target,count:0,ids:[],inherited:false};grouped.set(key,g);}g.count++;g.ids.push(e.id);g.inherited ||= !!e.payload.inherited;}
    const ids=new Set(nodesData.map(n=>n.id));
    linksData=[...grouped.values()].filter(e=>ids.has(e.source)&&ids.has(e.target));
    linkSel=linkG.selectAll('path').data(linksData,d=>d.id).join('path').attr('class',d=>'graph-edge'+(d.inherited?' inherited':''))
      .attr('marker-end','url(#arrow)').attr('stroke-width',d=>Math.min(4,1+Math.log2(d.count+1)*.45));
    linkSel.selectAll('title').data(d=>[d]).join('title').text(d=>`${d.count} recorded actions${d.inherited?' · shared checkpoint':''}`);
    nodeSel=nodeG.selectAll('g.state-card').data(nodesData,d=>d.id).join(enter=>{
      const g=enter.append('g').attr('class','state-card').attr('tabindex',0).attr('role','button');
      g.append('rect').attr('class','card-body').attr('x',-100).attr('y',-68).attr('width',200).attr('height',168).attr('rx',10);
      g.append('rect').attr('class','card-screen').attr('x',-94).attr('y',-62).attr('width',188).attr('height',100).attr('rx',5);
      g.append('image').attr('x',-94).attr('y',-62).attr('width',188).attr('height',100).attr('preserveAspectRatio','xMidYMid meet');
      g.append('text').attr('class','no-frame').attr('x',0).attr('y',-6).attr('text-anchor','middle');
      g.append('text').attr('class','card-title').attr('x',-88).attr('y',54);
      g.append('text').attr('class','card-variant').attr('x',-88).attr('y',83);
      g.append('text').attr('class','card-meta').attr('x',-88).attr('y',67);
      g.append('circle').attr('class','card-dot').attr('cx',87).attr('cy',53).attr('r',3);
      g.append('title');return g;
    }).classed('failed',d=>d.bad).classed('merged',d=>!d.bad&&d.arrivals>1)
      .attr('aria-label',d=>`${d.label}, depth ${d.depth}, ${d.arrivals} arrivals`)
      .on('click',(e,d)=>{e.stopPropagation();if(d.isPage){window.selectPage(d.page_key);toggleGroup(d.page_key);}else window.selectState(d.id);})
      .on('keydown',(e,d)=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();if(d.isPage){window.selectPage(d.page_key);toggleGroup(d.page_key);}else window.selectState(d.id);}}).call(drag());
    nodeSel.select('image').attr('href',d=>d.screenshot?artifact(d.screenshot):null);
    nodeSel.select('.no-frame').text(d=>d.screenshot?'':'Starting checkpoint');
    nodeSel.select('.card-title').text(d=>(d.label||'Application state').slice(0,27));
    nodeSel.select('.card-meta').text(d=>d.isPage?'PAGE GROUP · CLICK TO EXPAND':`VARIANT ${d.variant||'?'}  ·  ${d.arrivals} ARRIVALS  ·  ${d.arrival_paths??0} PATHS`);
    nodeSel.select('.card-variant').text(d=>(d.variant_note||'').slice(0,42));
    nodeSel.select('title').text(d=>d.label);
    const nextTopology=nodesData.map(n=>n.id).join()+linksData.map(e=>e.id).join();
    simulation.nodes(nodesData);simulation.force('link').links(linksData);
    if(nextTopology!==topology){topology=nextTopology;simulation.alpha(.55).restart();if(autoFit&&nodesData.length){for(let i=0;i<60;i++)simulation.tick();initialFit=true;ticked();fitToNodes();}}
    workers=workerList;renderWorkers();highlight(focused,selectedPath);ticked();
  }
  function renderWorkers(){
    const slots={};const visible=workers.filter(w=>nodesData.some(n=>n.id===w.state)).map(w=>({...w,slot:slots[w.state]=(slots[w.state]??-1)+1}));
    // Keep the map readable; the browser wall and Agents tab retain every worker.
    const grouped=Object.groupBy?Object.groupBy(visible,w=>w.state):visible.reduce((a,w)=>((a[w.state]??=[]).push(w),a),{});
    const markers=Object.values(grouped).flatMap(ws=>ws.slice(0,3).map((w,i)=>({...w,extra:i===2?ws.length-3:0})));
    const g=agentG.selectAll('.agent-marker').data(markers,d=>d.id).join(enter=>{
      const g=enter.append('g').attr('class','agent-marker').attr('tabindex',0).attr('role','button');
      g.append('rect').attr('x',-58).attr('y',-12).attr('width',116).attr('height',21).attr('rx',10);
      g.append('circle').attr('cx',-45).attr('cy',-2).attr('r',3);
      g.append('text').attr('x',-34).attr('y',2);return g;
    }).style('--worker-color',d=>workerColor(d.id)).on('click',(e,d)=>{e.stopPropagation();window.selectWorker(d.id);})
      .on('keydown',(e,d)=>{if(e.key==='Enter')window.selectWorker(d.id);}).attr('aria-label',d=>`Inspect ${d.id}`);
    g.select('text').text(d=>`${d.id.replace('worker-','W')}${d.extra?' +'+d.extra:''}`.slice(0,18));ticked();
  }
  function highlight(id,pathIds=new Set()){
    focused=id;selectedPath=pathIds;
    nodeSel.classed('focused',d=>d.id===id);
    linkSel.classed('path-selected',d=>d.ids.some(id=>pathIds.has(id)));
  }
  function pulse(edge,worker){
    const key=edge.source+'|'+edge.target;
    const path=linkSel.filter(d=>d.id===key).node();if(!path)return;
    const length=path.getTotalLength();
    const dot=pulseG.append('circle').attr('r',6).attr('fill',workerColor(worker)).attr('class','travel-dot');
    const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
    dot.transition().duration(reduced?0:1000).ease(d3.easeCubicInOut).attrTween('transform',()=>t=>{const p=path.getPointAtLength(t*length);return `translate(${p.x},${p.y})`;}).remove();
  }
  function toggleGroup(id){if(collapsedPages.has(id))collapsedPages.delete(id);else collapsedPages.add(id);autoFit=true;topology='';if(lastData)update(lastData,lastWorkers);}
  function collapseAll(){const all=pageGroups.every(g=>collapsedPages.has(g.id));collapsedPages=all?new Set():new Set(pageGroups.map(g=>g.id));autoFit=true;topology='';if(lastData)update(lastData,lastWorkers);}
  function arrival(id){const card=nodeSel.filter(d=>d.id===id);card.interrupt().classed('just-matched',true);setTimeout(()=>card.classed('just-matched',false),1500);}
  return {update,reset,highlight,pulse,fit:fitToNodes,resize,toggleGroup,collapseAll,arrival};
})();
