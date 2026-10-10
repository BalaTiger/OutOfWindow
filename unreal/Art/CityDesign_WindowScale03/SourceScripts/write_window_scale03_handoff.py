"""Write the local asset handoff only after actual final render and audits pass."""
import hashlib
import json
import shutil
import struct
from datetime import datetime, timezone
from pathlib import Path

workspace = Path(__file__).parent
project = Path(r'C:\Users\zhuzi\Documents\OutOfWindow')
out = project/'unreal/Art/CityDesign_WindowScale03'


def read(name):
    return json.loads((out/name).read_text(encoding='utf-8-sig'))


mesh = read('mesh_audit.json')
glb = read('export_audit.json')
fbx = read('fbx_roundtrip_audit.json')
assert mesh['status'] == glb['status'] == fbx['status'] == 'PASS'
log_bytes = (out/'finalize-v3.log').read_bytes()
log = log_bytes.decode('utf-16' if log_bytes.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig',errors='replace')
assert 'WINDOW_SCALE03_FINAL_CPU_COMPLETE' in log, 'Final CPU render not complete'
preview = out/'preview-window.png'
with preview.open('rb') as stream:
    header = stream.read(24)
assert header[:8] == b'\x89PNG\r\n\x1a\n'
assert struct.unpack('>II', header[16:24]) == (2560,1440)
now = datetime.now(timezone.utc).isoformat()

scripts = ['build_window_scale03.py','window_scale03_details.py','refine_window_scale03.py',
    'export_window_scale03.py','render_window_scale03.py','finalize_window_scale03.py',
    'review_export_window_scale03.py','validate_city_sample.py','new_curved_validation.py',
    'verify_window_scale03_exports.py','verify_window_scale03_fbx.py',
    'prepare_window_scale03.py','build_curved_sample.py','save_window_render_preset.py','write_window_scale03_handoff.py']
source_dir = out/'SourceScripts'
source_dir.mkdir(exist_ok=True)
for name in scripts:
    shutil.copy2(workspace/name, source_dir/name)

before = read('protected-before-v3.json')
protected = []
for record in before:
    path = project/record['relative_path']
    current = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    protected.append({**record,'current_sha256':current,'unchanged':current==record['sha256']})
protection = {'checked_utc':now,'status':'PASS' if all(r['unchanged'] for r in protected) else 'CHANGED',
    'scope':'Exact hashes of protected existing project files, old samples and base-only checkpoint captured before v3 edits.',
    'files':protected,'changed_files':[r['relative_path'] for r in protected if not r['unchanged']],
    'limitation':'This is a selected-file comparison, not a proof that all parallel work in the entire repository stayed unchanged.'}
(out/'protected-after-v3.json').write_text(json.dumps(protection,indent=2),encoding='utf-8')

manifest = read('design_manifest.json')
manifest['stage'] = 'Fixed-window CPU final image and independent source/GLB/FBX technical checks complete; visual acceptance pending.'
manifest['final_preview'] = {'file':'preview-window.png','width':2560,'height':1440,'engine':'Cycles','device':'CPU','threads':1,'samples':24,'denoising':True}
manifest['pixel_review'] = 'Only the fixed window image was used. Aesthetic remaining issues are in fixed_window_visual_review.json.'
manifest['refinements_file'] = 'fixed_window_refinements.json'
manifest['technical_reports'] = ['mesh_audit.json','export_audit.json','fbx_roundtrip_audit.json']
(out/'design_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')

review = {
    'status':'CANDIDATE_REQUIRES_USER_VISUAL_REVIEW',
    'reviewed_images':['../CityDesign_CurvedDistrict02/preview-window.png','window-draft-initial.png','window-draft.png','preview-window.png'],
    'camera':'Review_Window_UE_VFOV54 unchanged; position [26,-42,37], target [-22,115,19], VFOV54, aspect16:9.',
    'measurements_basis':'Approximate actual 1280x720 draft pixels, final uses same camera at 2x each dimension. Final image separately opened for visual verification.',
    'measurements_1280':{
        'A_band_px':[12,16],'A_glass_px':[45,47],'A_storey_px':[56,59],
        'B_band_px':[6,8],'B_glass_px':[23,25],'B_storey_px':[30,33],
        'bridge_body_height_px':[46,50],'bridge_front_width_px':[120,130],
        'bridge_glass_height_px':[23,24],'bridge_upper_and_lower_edge_px':[11,12],
        'under_bridge_opening_width_px':[45,55],'under_bridge_opening_height_px':[30,45],
        'ORBIT_letter_height_px':[6,8],'entry_visible_door_width_px':[15,22],
        'entry_north_reveal_width_px':[8,11],
        'front_office_secondary_mullion_px':[1,3],'front_office_floor_beam_px':[2,4]
    },
    'verified_improvements':['Thinner ordinary commercial bands and greater building breadth reduce thick toy-ring scale.',
        'Bridge body slimmer, three-storey deck aligned at G+8.8m, visible opening remains.',
        'ORBIT name visible on right of tree; door plane moved forward and north reveal shortened.',
        'Actual B07/B08/B13 metric masses preserved; narrower visible modules, physical opaque spandrels and applied corner caps.',
        'Correct office daytime color path; right/left office glass contrast improved without COLOR_0 multiplication.'],
    'remaining_visual_issues':['Repeated curved white lines and cool glass still dominate; doughnut/toy effect reduced, not eliminated.',
        'Stone service bays and bronze restaurant bays have weak functional distinction at the fixed-window distance.',
        'Central office remains pale against the sky.',
        'Tree still obscures left half of main entrance; full entrance envelope remains visually bulky.',
        'Dark B entrance backing reduces perception of court depth under the bridge.'],
    'not_tested':['Native UE materials/rendering/import/runtime/GPU','UV island overlap and lightmap bake','Self-intersections and physical accessibility/collision'],
    'technical_pass_is_not_visual_acceptance':True
}
(out/'fixed_window_visual_review.json').write_text(json.dumps(review,indent=2),encoding='utf-8')

README = '''# 固定窗景建筑候选 WindowScale03

这是独立可编辑候选，仍待用户审美审阅。只使用 `Review_Window_UE_VFOV54` 固定相机验收，没有新近景或绕行镜头。没有启动 UE、使用 GPU、改 City 地图或部署。

## 首先查看

- `preview-window.png`：2560×1440，Cycles CPU，单线程，24 samples＋降噪。
- `CityDesign_WindowScale03.blend`：购物中心 A/B、连桥、街庭和原窗景城市背景；可编辑网格按用途保留命名。导出副本在隐藏的 `Export_WindowScale03` 集合。
- `CityDesign_WindowScale03_Commercial.glb/.fbx`：4 个网格，A、B、连桥、街庭，共 151,988 三角。
- `CityDesign_WindowScale03_OfficeVisible.glb/.fbx`：原实际 B07/B08/B13 三栋的候选版本，共 65,218 三角；可见玻璃及细部修正，背面保留原简单面。
- `fixed_window_visual_review.json`：实际像素复核、改善与剩余问题。

## 比例与设计

Blender 1 单位＝1 米；UE 厘米坐标为 `(100*BX, -100*BY, 100*BZ)`。glTF 自带标准 Y-up 转换，勿重复交换轴；FBX 已启用单位换算，实际回读边界一致。相机位置 `(26,-42,37)`、目标 `(-22,115,19)`、垂直 FOV 54°、16:9。

购物中心设计沿用已确认的 Galaxy SOHO 建成照片方向，但不是其复刻。A 外包络约 33.47×36.81 米、高 22.34 米，5 个商业层；B 约 38.90×42.89 米、高 27.74 米，6 个商业层。普通层高 A 4.15 米、B 4.35 米；普通外檐横截面高 0.89 米，退台与屋顶服务屏独立。入口玻璃门高约 2.78 米，檐口下保留可识别门扇、把手、横梃和暖色内厅。少数服务面使用 60 毫米石材与 45 毫米铜色实体板。

连桥桥面绝对 Z=15.70 米，与 A/B 的 G+8.80 层对齐；中间宽 4.40 米、两端 6.20 米；桥下最低净空约 8.12 米；全外包络约 12.31×19.74×4.49 米。C 是旧占位体，存储但隐藏、不导出，不作完成建筑。

办公楼采用原 City 的真实体量：B07 下部 5 层×3.30 米、上部 3 层×约3.72 米；B08 13 层×约3.29 米；B13 18 层×约3.27 米。原约 2.8–2.9 米玻璃模块各分为两个模块，52 毫米次竖梃、43 毫米窗头轨、32 毫米闭合玻璃与 550 毫米窗下实体板。共替换 771 个原可见模块为 1,542 个半模块，未改原办公体量。

固定图中 A/B 普通白带约12–16／6–8像素（1280×720），较旧22–27／11–13下降；桥舱高46–50、宽120–130像素，主门标牌约6–8像素字高，右前办公次竖梃约1–3像素。最终分辨率每轴2倍。继续细化以屏幕可见性为依据，不能把增加面数当作质量通过。

## 尚未达到审美通过

曲线白带与冷色玻璃仍有重复感；石材/铜色服务分段在固定窗景距离下辨识弱。中间办公楼仍浅白，树仍遮住主入口左半。ORBIT 已在树冠右侧可辨，门柱缩窄，但门厅整体仍显粗大。这些都已明确记录，技术 PASS 不代表用户接受。

源 City 的 `COLOR_0` 是 UE 夜间发光载荷。候选日间预览移除了错误的 Base Color 乘法，办公导出副本移除颜色属性；原 GLB/UE 材质没有更改。候选 PBR 与 Blender 天空光只能用于此次 CPU 预览，不能宣称已验证 UE 效果。

## 技术验证与保护证据

- `mesh_audit.json`：319 个新增可编辑网格、208,248 三角（含隐藏 C 的316三角），双 UV、有限几何、正常法线、材料分配和闭合壳朝向检查 PASS。明确许可开放字体，不宣称所有文字完全封闭。
- `export_audit.json`：独立 Python 直接解析实际 GLB 字节；商业4实例＋办公3实例、双UV、单位法线、合法索引、非退化三角、世界边界、无办公COLOR_0、无C/背景/相机/灯光导出，PASS。
- `fbx_roundtrip_audit.json`：实际两份 FBX 在临时空 Blender 场景回读；7个网格、双UV、法线、三角数与边界（0.1毫米容差）PASS。临时场景未保存覆盖源文件。
- `protected-before-v3.json`／`protected-after-v3.json`：指定旧资产、旧预览、City/脚本、WindowDirector 和 base-only 副本的哈希对照。查阅后者的实际状态；不是整个仓库的并行工作证明。

未验证 UV 岛重叠/烘焙、碰撞、自交、施工/结构安全、UE 导入和材质转换、运行时性能。不把所有内外表面积相除当作立面玻璃比例。

## 工具、建模方式与恢复

Blender 5.0.1 位于 `D:\\Blender\\blender.exe`。本机工具采用 Blender 后台执行明确截面、门厅、板件及网格编辑；不是 GUI 手工操作，也不是随机盒子或 Geometry Nodes 城市生成器。普通曲面采用明确控制点与截面，源网格保持可编辑。

直接打开主 `.blend` 可继续编辑。`SourceScripts` 保存此次实际脚本；重建需要先运行 `build_window_scale03.py`，再 `refine_window_scale03.py`，最后 `finalize_window_scale03.py`（它会导出、验证并只渲染最终固定图）。源底板为 `CityDesign_WindowScale03_CHECKPOINT_BASE_ONLY.blend`，不可覆盖。`prepare_window_scale03.py` 只作最初派生记录，恢复时不要重跑以覆盖保护基线。

继续遵守单 Blender 进程、CPU 单线程、不抢桌面焦点。UE 试摆、GPU 或高负载渲染需先通知主会话协调云层和 ToE 浏览器测试时段。没有 Git 提交、推送或部署。
'''
(out/'README.md').write_text(README,encoding='utf-8')

RESUME = '''# 恢复说明：WindowScale03 独立候选已完成本轮

原来的关机暂停指令已由主会话明确取消；2026-10-07 已恢复并完成两轮固定窗景修正、导出与技术验证。当前主文件是 `CityDesign_WindowScale03.blend`，不是 `CHECKPOINT_BASE_ONLY`。

先查看 `README.md`、`preview-window.png` 和 `fixed_window_visual_review.json`。正式图2560×1440，仅固定相机；没有新近景。当前是待用户审阅候选，不能宣称审美通过：商场功能分段在该距离弱、中楼偏浅、入口左半仍被树遮挡。

三个技术报告均PASS，商业4网格151,988三角＋办公3网格65,218三角。原文件保护状态看 `protected-after-v3.json`；工具/尺度/完整文件索引见 `README.md` 和 `file-index.json`。

继续编辑直接打开主 `.blend`；C占位隐藏，导出副本隐藏。`SourceScripts` 为实际可复现脚本。base-only 副本原样受保护，勿覆盖；`prepare_window_scale03.py` 勿重跑覆盖哈希基线。

仅在独立城市美术目录修改；保留原City、WindowDirector、云材质、共享脚本和现有工作树改动。单进程CPU低负载；UE导入/地图试摆/GPU之前通知主会话协调时段。没有授权整城扩建、Git提交推送或替换部署。
'''
(out/'RESUME.md').write_text(RESUME,encoding='utf-8')

PLAN = '''# 本轮计划与完成文件

1. 恢复本机 Blender/哈希基线并只读核对原 City 相机、办公尺寸与旧固定窗景像素：完成。
2. 界定共享尺度和可见细节预算，在独立候选修正商场 A/B、连桥及实际 B07/B08/B13 可见表面：完成。
3. 两轮1280×720 CPU固定小样复核，入口、实体服务面、办公窗下板有限修正：完成；明确仍未审美通过。
4. 实际 GLB 与 FBX 导出验证、源网格审计及2560×1440唯一固定正式图：完成。
5. 保护证据、可编辑源文件、恢复说明、源脚本、文件/哈希索引：完成。

主交付：`CityDesign_WindowScale03.blend`、`preview-window.png`、`CityDesign_WindowScale03_Commercial.glb/.fbx`、`CityDesign_WindowScale03_OfficeVisible.glb/.fbx`。验证与说明：`README.md`、`RESUME.md`、`checkpoint-status.json`、三个审计JSON、`fixed_window_visual_review.json`、`fixed_window_refinements.json`、`file-index.json`、`protected-after-v3.json`。实际源脚本在 `SourceScripts`。

下一步是用户对候选的固定图审阅。UE导入与地图试摆不在本轮，需主会话协调时段后安排。无部署、无Git提交、无整城扩建。
'''
(out/'PLAN.md').write_text(PLAN,encoding='utf-8')

status = {'updated_utc':now,'state':'LOCAL_CANDIDATE_COMPLETE_VISUAL_REVIEW_PENDING',
    'blender_version':'5.0.1','blender_executable':r'D:\Blender\blender.exe',
    'main_blend':'CityDesign_WindowScale03.blend','base_checkpoint_unchanged':True,
    'cpu_fixed_preview':'preview-window.png','preview_size':[2560,1440],
    'technical_status':{'source_mesh':'PASS','actual_glb_bytes':'PASS','fbx_readback':'PASS'},
    'protected_selected_files_status':protection['status'],
    'source_new_mesh_triangles_including_hidden_C':208248,
    'export_commercial_triangles':151988,'export_office_triangles':65218,
    'visual_accepted':False,'remaining_visual_issues':review['remaining_visual_issues'],
    'ue_import_map_edit_gpu_git_commit_deploy':False,
    'next_action':'Main-session fixed-window visual review; coordinate before UE/GPU work.'}
(out/'checkpoint-status.json').write_text(json.dumps(status,indent=2),encoding='utf-8')

records = []
for path in sorted(out.rglob('*')):
    if not path.is_file() or path.name == 'file-index.json':
        continue
    records.append({'relative_path':path.relative_to(out).as_posix(),'bytes':path.stat().st_size,
                    'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(out/'file-index.json').write_text(json.dumps({'updated_utc':now,'files':records},indent=2),encoding='utf-8')
print('WINDOW_SCALE03_LOCAL_HANDOFF_WRITTEN', 'protected='+protection['status'], 'files='+str(len(records)))
