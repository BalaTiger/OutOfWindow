"""Create a new runtime-only derived material; never edit accepted cloud assets.

Run once with UE Python commandlet. Runtime v2 adds a complementary horizontal
distance blend for few-cloud weather. All accepted shape/cirrus code is retained.
"""
import unreal as u
from pathlib import Path
import hashlib,json

PROJECT=Path(u.Paths.project_dir()).resolve()
REPO=PROJECT.parents[1]
OUT=REPO/'.runtime/cloud-runtime-sync-20261019'
OUT.mkdir(parents=True,exist_ok=True)
OLD='/Game/Weather/OOW_ApprovedClouds'
NEW='/Game/Weather/OOW_RuntimeClouds_20261019'
LIB=u.MaterialEditingLibrary

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
protected={p.name:sha(p) for p in (PROJECT/'Content/Weather/OOW_ApprovedClouds').glob('*.uasset')}
assert len(protected)==3
for name in ('M_RuntimeMix_v2','MI_RuntimeMix_v2'):
    assert not u.EditorAssetLibrary.does_asset_exist(NEW+'/'+name), 'Existing version must not be overwritten'
master=u.EditorAssetLibrary.duplicate_asset(OLD+'/M_RuntimeMix',NEW+'/M_RuntimeMix_v2')
instance=u.EditorAssetLibrary.duplicate_asset(OLD+'/MI_RuntimeMix',NEW+'/MI_RuntimeMix_v2')
assert master and instance
prefix=master.get_path_name()+':'
nodes=[n for n in u.ObjectIterator(u.MaterialExpression) if n.get_path_name().startswith(prefix)]
def param(name):
    candidates=[n for n in nodes if isinstance(n,(u.MaterialExpressionVectorParameter,u.MaterialExpressionScalarParameter)) and str(n.get_editor_property('parameter_name'))==name]
    assert len(candidates)==1,(name,len(candidates))
    return candidates[0]
mix=param('OOW_ApprovedMix');origin=param('OOW_ApprovedOriginKm')
positions=[n for n in nodes if isinstance(n,u.MaterialExpressionWorldPosition)]
assert positions
before={n.get_name():str(n.get_editor_property('code')) for n in nodes if isinstance(n,u.MaterialExpressionCustom)}
few=LIB.create_material_expression(master,u.MaterialExpressionScalarParameter,-1800,-1800)
few.set_editor_property('parameter_name','OOW_ApprovedFewFar');few.set_editor_property('default_value',0.)
distance=LIB.create_material_expression(master,u.MaterialExpressionVectorParameter,-1800,-1600)
distance.set_editor_property('parameter_name','OOW_ApprovedDistanceKm');distance.set_editor_property('default_value',u.LinearColor(4,8,0,0))
code='''
// Runtime-only routing. Accepted density and high cirrus remain unchanged.
float distanceKm=length(Position.xy*.00001-Origin.xy);
float t=saturate((distanceKm-DistanceKm.x)/max(DistanceKm.y-DistanceKm.x,.001));
t=t*t*(3.0-2.0*t);
float full=saturate(OriginalMix.r);
float light=full+(1.0-full)*saturate(FewFar)*t;
return float4(light,1.0-light,OriginalMix.b,OriginalMix.a);
'''
blend=LIB.create_material_expression(master,u.MaterialExpressionCustom,-1300,-1800)
blend.set_editor_property('description','OOW runtime v2 complementary few-cloud near/far routing')
blend.set_editor_property('code',code)
blend.set_editor_property('output_type',u.CustomMaterialOutputType.CMOT_FLOAT4)
pins=[]
for name in ('OriginalMix','FewFar','DistanceKm','Position','Origin'):
    pin=u.CustomInput();pin.set_editor_property('input_name',name);pins.append(pin)
blend.set_editor_property('inputs',pins)
for source,output,pin in ((mix,'RGBA','OriginalMix'),(few,'','FewFar'),(distance,'RGBA','DistanceKm'),(positions[0],'','Position'),(origin,'RGBA','Origin')):
    assert LIB.connect_material_expressions(source,output,blend,pin),pin
rewired=[]
for node in nodes:
    sources=LIB.get_inputs_for_material_expression(master,node)
    names=list(map(str,LIB.get_material_expression_input_names(node)))
    for pin,source in zip(names,sources):
        if source==mix:
            assert LIB.connect_material_expressions(blend,'',node,pin),(node.get_name(),pin)
            rewired.append(dict(node=node.get_name(),pin=pin))
assert len(rewired)>=4,rewired
for node in nodes:
    if isinstance(node,u.MaterialExpressionCustom): assert str(node.get_editor_property('code'))==before[node.get_name()]
LIB.set_material_instance_parent(instance,master)
LIB.recompile_material(master)
u.EditorAssetLibrary.save_loaded_asset(master,only_if_is_dirty=False)
u.EditorAssetLibrary.save_loaded_asset(instance,only_if_is_dirty=False)
assert all(sha(PROJECT/'Content/Weather/OOW_ApprovedClouds'/name)==value for name,value in protected.items())
proof=dict(status='NEW_DERIVED_RUNTIME_V2_SAVED',master=master.get_path_name(),instance=instance.get_path_name(),protectedAssets=protected,acceptedCustomCodeUnchanged=True,cirrusBundleDirectionUnchanged=True,newParameters=['OOW_ApprovedFewFar','OOW_ApprovedDistanceKm'],nearKm=4,farKm=8,rewired=rewired,code=code,originalCustomCodeSHA256={k:hashlib.sha256(v.encode()).hexdigest() for k,v in before.items()},assets={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in (PROJECT/'Content/Weather/OOW_RuntimeClouds_20261019').glob('*.uasset')})
(OUT/'material-v2-result.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
(OUT/'accepted-custom-code.json').write_text(json.dumps(before,indent=2),encoding='utf-8')
print(json.dumps(proof))
