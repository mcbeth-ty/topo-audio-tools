// Run with: node harmony-generator/test_ambient_pathfinder.mjs
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source=fs.readFileSync(new URL('./ambient_frontend/study_pathfinder.js',import.meta.url),'utf8');
const scope=vm.createContext({});vm.runInContext(source,scope);
const {studyPathGraph:graph,studyPathRoutes:routes}=scope;
const pair=(a,b,strength,count=1)=>({ids:[a,b],relatedness:strength,valid_count:count});
const ids=['a','b','c','d','e'],coordinates={a:[0,0,0],b:[1,0,0],c:[2,0,0],d:[1,1,0],e:[20,0,0]};
const pairs={ab:pair('a','b',3),bc:pair('b','c',3),ac:pair('a','c',1),ad:pair('a','d',2),dc:pair('d','c',2),ce:pair('c','e',0),ae:pair('a','e',3,0)};
const g=graph(ids,coordinates,pairs),result=routes(g,'a','c');
assert.equal(result.length,3);
assert.equal(JSON.stringify(result[0].nodes),JSON.stringify(['a','b','c']));
assert.equal(result[0].cost,2);assert.equal(result[0].distance,2);
assert.equal(JSON.stringify(result[1].nodes),JSON.stringify(['a','d','c']));
assert.equal(JSON.stringify(result[2].nodes),JSON.stringify(['a','c']));
assert(result.every((r,i)=>new Set(r.nodes).size===r.nodes.length&&(!i||r.cost>=result[i-1].cost)));
assert.equal(routes(g,'a','e').length,0);
assert.equal(JSON.stringify(result),JSON.stringify(routes(g,'a','c')));
// Fourth-coordinate separation is included, and cannot mutate coordinates.
const before=JSON.stringify(coordinates),four={x:[0,0,0,0],y:[0,0,0,4]};
assert.equal(graph(['x','y'],four,{xy:pair('x','y',3)}).get('x').get('y'),4);
assert.equal(JSON.stringify(coordinates),before);
// Compare the first three routes with exhaustive simple-path enumeration.
function exhaustive(graph,start,end){
 const output=[];function walk(path,cost){const last=path.at(-1);if(last===end){output.push({nodes:path,cost});return;}
 for(const [next,w] of graph.get(last))if(!path.includes(next))walk([...path,next],cost+w);}
 walk([start],0);return output.sort((a,b)=>a.cost-b.cost||a.nodes.join('|').localeCompare(b.nodes.join('|'))).slice(0,3);
}
for(let seed=0;seed<25;seed++){
 const coords=Object.fromEntries(ids.map((id,i)=>[id,[i,(seed*(i+3)%11)/7,0]])),p={};
 for(let i=0;i<ids.length;i++)for(let j=i+1;j<ids.length;j++)p[`${i}|${j}`]=pair(ids[i],ids[j],(seed+i*3+j)%4);
 const graph_=graph(ids,coords,p),actual=routes(graph_,'a','e'),expected=exhaustive(graph_,'a','e');
 assert.equal(actual.length,expected.length);
 for(let i=0;i<actual.length;i++){assert(Math.abs(actual[i].cost-expected[i].cost)<1e-10);assert.equal(JSON.stringify(actual[i].nodes),JSON.stringify(expected[i].nodes));}
}
console.log('PASS: strength-prioritized routing, three exact loopless alternatives, Weak+ filtering, disconnected cases, deterministic ties, full 4D distance, and exhaustive small-graph comparison.');
