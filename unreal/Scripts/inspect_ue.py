import unreal
from pathlib import Path

output = Path(unreal.Paths.project_dir()).parent / 'Migration' / 'ue-api.txt'
output.parent.mkdir(parents=True, exist_ok=True)
names = ['InterchangeManager', 'ImportAssetParameters', 'InterchangeGenericAssetsPipeline',
         'InterchangeGenericScenesPipeline', 'InterchangeGenericMeshPipeline', 'InterchangeGenericMaterialPipeline',
         'InterchangeGLTFTranslatorSettings', 'StaticMeshEditorSubsystem', 'EditorLevelLibrary',
         'MaterialEditingLibrary', 'MeshNaniteSettings', 'StaticMeshReductionOptions',
         'StaticMeshReductionSettings', 'MaterialExpressionCustom', 'MaterialParameterCollection',
         'MaterialExpressionCollectionParameter']
with output.open('w', encoding='utf-8') as f:
    for name in names:
        cls = getattr(unreal, name, None)
        f.write('\n### ' + name + '\n' + str(getattr(cls, '__doc__', None)) + '\n')
        if cls:
            for method in dir(cls):
                if any(t in method for t in ['import_scene', 'import_asset', 'nanite', 'lod', 'create_source', 'collection']):
                    f.write(method + ': ' + str(getattr(cls, method).__doc__) + '\n')
unreal.log('OOW_API_INSPECTION_COMPLETE')
