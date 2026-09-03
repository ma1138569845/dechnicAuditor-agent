# 第3章：能源资源管理状况 — 生成指南

> 本指南对齐当前代码：
> - `tools/energy_audit/report_generator.py` — `build_chapter3()` / `load_from_project()` / `_energy_saving_chapter3_sections()`
> - `tools/energy_audit/file_resolver.py` — `enrich_management_info()`（采集阶段制度文件提炼）
> - `tools/energy_audit/llm_client.py` — `summarize_management_docs()`（LLM 提炼 3.1/3.2）
> - `tools/energy_audit/imitate_pipeline.py` — 仿写管道（新参考模式）

---

## 章节结构（共 4 节 + 图片）

| 节号 | 标题 | 主要数据源 | 为空时行为 |
|---|---|---|---|
| 3.1 | 能源资源管理机构职责 | `proj.management.management_org` | 通用兜底句；author 可再按机构类型模板填充 |
| 3.2 | 能源资源管理目标和方针 | `proj.management.management_policy` + `es.energy_management` | 无数据时：**仿写同类报告 3.2**（首选）或通用兜底句 |
| 3.3 | 能源资源管理成效与问题 | `proj.management.honors` + `es.has_awards` / `award_name` / `energy_pain_points` | 通用兜底句 |
| 3.4 | 节能改造与管理措施 | `es` 各改造字段（见下） | **无数据时不渲染该节** |
| 图片 | 管理文件 / 荣誉证书照片 | `es.management_file_images` + `award_certificate_images` + `images[]` 分类 | 无则跳过 |

> ⚠️ **3.4 是最容易漏的一节**：`build_chapter3()` 会渲染 `section_3_4`，凡节能管理信息（`ts_institution_energy_saving`）中有改造措施字段即自动生成该节。写作时必须包含 3.4。

---

## 生成模式

**第3章文本由 `load_from_project()` 自动从项目数据组装**，author 的职责是：在自动文本偏单薄或缺失时，基于字段数据 + 模板 + 参考句式增强为自然段落。三种方式：

1. **自动组装（默认）**：`load_from_project()` 读取 `project.management` 与最新一条 `project.energy_saving`（按 `statistical_year` 降序取第一条），组装 `report_data.chapter3` 的 `section_3_1`~`section_3_4` 与 `images`。采集阶段 `enrich_management_info` 已由制度文件 LLM 提炼正文，通常无需 author 重写。
2. **仿写参考（参考同类报告）**：调用 `energy_audit_imitate_paragraph` 工具或 `/api/energy-audit/imitate` 接口，检索同类报告第3章并按段落结构仿写正文：
   ```python
   # 直接调用（项目名 = proj.base.unit_name）
   run_imitate("莘县县政府", chapter="第3章", section="3.1 机构职责")
   ```
   ```bash
   # CLI 方式
   python -m tools.energy_audit.imitate_pipeline --project 莘县县政府 --chapter 第3章
   ```
   章节上下文：`imitate_pipeline.CHAPTER_CONTEXTS["第3章"] = "能源资源管理状况"`；`normalize_chapter("3.1")` 会自动归一为 `(第3章, 3.1)`。
3. **LLM 增强写作**：自动文本不足时，author 基于「数据来源」字段 + 本指南模板/句式，用 `set_report_data()` 或直接覆盖 `report_data['chapter3']['section_3_X']` 重写该节（写法：先 `load_project()` → `load_from_project()` 组装 → 覆盖薄弱节 → 再传给生成器）。

**必须提供照片**：管理文件截图、节能荣誉证书等现场照片（数据模型按分类路由，见「图片路由」节）。嵌入方式同第2章（`_add_image_with_caption`）。

---

## 3.1 能源资源管理机构职责

**数据源（优先）**：`proj.management.management_org` —— 采集阶段 `enrich_management_info()` 已下载制度文件并 LLM 提炼组织架构/岗位/职责分工，回填此字段。

- **非空**：直接作为 3.1 正文。段落组织参考：落实节能国策与上级会议精神 → 引用制度文件名称 → 管理机构设置 → 职责表述（取自提炼结果）。
- **为空**：`build_chapter3()` 会输出通用兜底句（"按《公共机构节能条例》要求，设立能源管理岗位和责任人…"）。author 可按下表按机构类型填充模板，占位符 `XX` 替换为被审计单位实际名称，并结合单位实际微调（禁止照抄其他单位的具体名称）。

**机构类型映射**（`proj.base.institution_category` 取值：医疗/教育/党政机关/场馆机构/体育/政务服务中心）：

| institution_category | 使用模板 |
|---|---|
| 医疗 | 医疗机构模板 |
| 教育 | 学校教育模板 |
| 党政机关 / 政务服务中心 | 党政机关模板 |
| 场馆机构 / 体育 / 其他 | 通用模板 |

**医疗机构模板**：

> XX各部门能够认真落实节约能源基本国策和省节能工作会议精神，切实加强建筑节能降耗工作，出台关于节水、节电等各类能源管理相关文件，并结合建筑实际情况，设置能源设备管理机构，并安排专人管理设备运行。同时，成立专门的工作领导小组，在节能降耗工作中取得了实效。
>
> 为推动单位节能工作，XX制定并实施了节能减排管理措施，成立节能工作小组，负责单位节能工作的安排部署、制度制定、检查通报等事宜。具体职责包括：
>
> 1.统筹节能工作规划：制定医院节能工作的中长期规划和年度计划，明确节能目标（如能耗降低指标）、重点任务及实施步骤，确保节能工作有序推进。
> 2.完善节能管理制度：建立和健全医院节能相关制度（如用电、用水、用热管理规定，设备节能运行规范等），明确各部门、各区域的节能责任，形成常态化管理机制。
> 3.开展节能宣传教育：组织节能主题活动（如节能周、知识讲座、竞赛等），普及节能知识和技能，引导员工养成节能习惯，营造"人人参与节能"的单位氛围。

**党政机关模板**：

> XX各部门能够认真落实节约能源基本国策和省节能工作会议精神，切实加强建筑节能降耗工作，出台关于节水、节电等各类能源管理相关文件。并结合建筑实际情况，设置能源设备管理机构，并安排专人管理设备运行。同时，成立专门的工作领导小组，在节能降耗工作中取得了实效。 
> 
> 为推动单位节能工作，XX制定并实施了节能减排管理措施，成立节能工作小组，负责单位节能工作的安排部署、制度制定、检查通报等事宜。具体职责包括： 
> 1.统筹节能工作规划：制定节能工作的中长期规划和年度计划，明确节能目标（如能耗降低指标）、重点任务及实施步骤，确保节能工作有序推进。 
> 2.完善节能管理制度：建立健全的节能相关制度（如用电、用水、用暖管理规定，设备节能运行规范等），明确各部门、各区域的节能责任，形成常态化管理机制。 
> 3.开展节能宣传教育：组织节能主题活动（如节能周、知识讲座、竞赛等），普及节能知识和技能，引导机关全体成员养成节能习惯，营造"人人参与节能"的办公室氛围。 

**学校教育模板**：

> XX各部门能够认真落实节约能源基本国策和省节能工作会议精神，切实加强建筑节能降耗工作，出台关于节水、节电等各类能源管理相关文件。并结合建筑实际情况，设置能源设备管理机构，并安排专人管理设备运行。同时，成立专门的工作领导小组，在节能降耗工作中取得了实效。 
> 
> 为推动单位节能工作，XX制定并实施了节能减排管理措施，成立节能工作小组，负责单位节能工作的安排部署、制度制定、检查通报等事宜。具体职责包括： 
> 1.统筹节能工作规划：制定学校节能工作的中长期规划和年度计划，明确节能目标（如能耗降低指标）、重点任务及实施步骤，确保节能工作有序推进。 
> 2.完善节能管理制度：建立和健全校园节能相关制度（如用电、用水、用暖管理规定，设备节能运行规范等），明确各部门、各区域的节能责任，形成常态化管理机制。 
> 3.开展节能宣传教育：组织节能主题活动（如节能周、知识讲座、竞赛等），普及节能知识和技能，引导师生养成节能习惯，营造"人人参与节能"的校园氛围。

**场馆 / 体育 / 政务服务中心等其他类型通用模板**：

> XX各部门能够认真落实节约能源基本国策和省节能工作会议精神，切实加强建筑节能降耗工作，出台关于节水、节电等各类能源管理相关文件。并结合建筑实际情况，设置能源设备管理机构，并安排专人管理设备运行。同时，成立专门的工作领导小组，在节能降耗工作中取得了实效。 
> 为推动单位节能工作，XX制定并实施了节能减排管理措施，成立节能工作小组，负责单位节能工作的安排部署、制度制定、检查通报等事宜。具体职责包括： 
> 1.统筹节能工作规划：制定单位节能工作的中长期规划和年度计划，明确节能目标（如能耗降低指标）、重点任务及实施步骤，确保节能工作有序推进。 
> 2.完善节能管理制度：建立和健全单位节能相关制度（如用电、用水、用暖管理规定，设备节能运行规范等），明确各部门、各区域的节能责任，形成常态化管理机制。 
> 3.开展节能宣传教育：组织节能主题活动（如节能周、知识讲座、竞赛等），普及节能知识和技能，引导办公人员养成节能习惯，营造"人人参与节能"的单位氛围。 

**关键要素**：政策落实情况、制度文件、管理机构、主要负责人/部门。

> **机构等级自适应**：措辞按被审计单位行政等级调整，不要硬套"印发"——省级→厅级单位→印发工作要点；县级→中心/机关事务服务中心→印发通知。撰写"牵头成立/印发文件/部署落实"等表述时先确认单位等级。

---

## 3.2 能源资源管理目标和方针（含管理制度）

**数据源（两段合并，优先级从上到下）**：

1. `proj.management.management_policy` —— `enrich_management_info()` 由制度文件 LLM 提炼的「管理目标 + 管理方针」**合并为一段**回填（`summarize_management_docs` 返回的 `goals_policy`）。非空时作为正文。
2. `es.energy_management`（`_energy_saving_chapter3_sections` 生成「管理制度」句，**仅当上面 `management_policy` 为空时**叠加，`report_generator.py:2844`）：
   - `energy_management == 1`：`"{unit}已建立能源管理制度，将节能管理纳入日常运营，通过制度建设、定期监督等方式落实节能责任。"`
   - `energy_management == 0`：`"{unit}目前尚未建立完善的能源管理制度，节能管理仍有提升空间。"`
   - `None`（未填写）：不生成，走兜底。

> ⚠️ `management_goals` 字段**当前流水线未消费**（`load_from_project()` 只读 `management_policy`）。若某项目单独填了 `management_goals`，author 可将其并入正文；但不要假设它会自动出现。

**为空时的兜底与增强**：

①、② 均无数据（无制度文件附件、无法提炼）时，**首选仿写同类报告 3.2 段落**：

- 调用 `run_imitate(项目名, chapter="第3章", section="3.2 管理目标和方针")`，或 CLI：`python -m tools.energy_audit.imitate_pipeline --project XX --chapter 第3章`
- 仿写范围=**段落结构与句式风格**；机构名、制度文件名称、荣誉等具体信息必须替换为本单位实际（未知则标【待补充】），**禁止照抄其他单位名称**
- 仿写后仍需与字段互核：`es.energy_management == 0` 时不得写成"已建立完善制度"，`== None` 时不得虚构制度名
- 仿写不可用时（无同类报告），再走下面兜底：

`build_chapter3()` 输出通用兜底句（"坚持'节约优先、高效利用'的能源管理方针…"）。author 可模板填充：

**引言段参考句式**：

> XX以习近平新时代中国特色社会主义思想为指导，认真贯彻落实党中央、国务院决策部署和省、市工作要求，聚焦绿色低碳中心工作，强化能源资源全面节约，持续实施绿色低碳引领行动，全面推进各项工作高质量发展。

**编号列表**（作为目标/方针的具体展开，根据单位实际选择 5~9 项；带"←"的为条件项，有对应设施/项目才加入）：
- 一、树立绿色发展理念
- 二、落实能耗"双控"目标
- 三、积极开展示范创建
- 四、坚持反对食品浪费
- 五、做好宣传教育培训
- 六、推进生活垃圾分类（← 有食堂/物业才加）
- 七、深化绿色低碳改造（← 有改造项目才加）
- 八、加强节水护水工作（← 有用水系统才加）
- 九、夯实能源资源消费统计（← 有监测系统才加）

注意：不同机构类型侧重不同——行政机关侧重办公节能+示范创建，医院侧重医疗设备节能+院感控制。

---

## 3.3 能源资源管理成效与问题

**结构：成效 + 问题**。

**数据源**：

- **成效**：`proj.management.honors`（已获节能荣誉）；另 `es.has_awards == 1` 且 `es.award_name` 非空时生成 `"{unit}节能工作取得成效，{award_name}。"`（`report_generator.py:3054`）。
- **问题**：`es.energy_pain_points`（能源利用痛点字段，`report_generator.py:3056` 生成 `"目前能源利用方面存在的主要痛点：{energy_pain_points}。"`）。
- author 增强时，可将上述真实数据组织为连贯段落，参考句式：

> XX在推进节能工作的进程中，已获得了XXX等荣誉。但对照节能工作要求，仍存在一定改进空间：一是XXX；二是XXX；三是XXX。

> ⚠️ 问题必须来自实际字段（`energy_pain_points` / 计量 / 设备 / 建筑推断），禁止编造。可结合第6章设备数据、第7章问题推断充实，但**不得虚构荣誉或问题**。
> 措辞宜柔化、避免尖锐，用"有待加强 / 进一步完善 / 逐步更新"；典型表述如"监测数据分析能力弱、老旧设备能效低、培训力度不足"。

---

## 3.4 节能改造与管理措施

**数据源**：最新一条 `es`（`ts_institution_energy_saving`）的改造字段，无对应数据时**不生成、不渲染此节**。各字段生成规则（`_energy_saving_chapter3_sections`）：

| 字段 | 条件 | 生成文案 |
|---|---|---|
| `lighting_replacement` | ==1 | `"{unit}已实施照明灯具更换等节能改造措施。"` |
| `ac_replacement` | ==1 | 同上，并入「照明灯具、空调设备更换…」 |
| `water_saving_fixture_replacement` | ==1 | 并入「…、节水型卫生器具更换…」 |
| `central_ac_control` | ==1 | "中央空调系统已增加集中控制，以提升运行能效。" |
| `other_measures` | 非空 | "其他节能改造措施：{other_measures}。" |
| `third_party_system` | 非空 | "能源系统已由第三方托管运营：{third_party_system}。" |
| `charging_pile` | ==1 | "单位已配置充电桩" + 结算方式/安装方式 |
| `third_party_outsource` | ==1 | "用能系统已由第三方外包管理" + 内容/结算方式 |

> ⚠️ author 扩写此节时，只能基于上述真实字段展开，禁止新增未记录的措施。第三方托管/外包、充电桩等均须取自 `es` 字段。

---

## 图片路由

第3章图片来源共三处（`load_from_project` 自动合并，`report_generator.py:2847-2854`）：

1. `es.management_file_images`（管理制度附件解析下载后的**本地路径列表**）
2. `es.award_certificate_images`（获奖证书附件下载后的本地路径）
3. `proj.images[]` 中 `category == '管理文件/荣誉'` 的 `ImageItem`（数据采集阶段已分类）

caption 自动编号（图3-1、图3-2…），嵌入用 `_add_image_with_caption(path, caption)`。`PHOTO_CATEGORIES` 中该分类名为 **`'管理文件/荣誉'`**（不是"管理文件截图"），路由键必须一致。

---

## report_data.chapter3 结构

`load_from_project()` 组装，author 可用 `set_report_data()` 覆盖或直接改 `report_data['chapter3']`：

```python
chapter3 = {
    'section_3_1': project.management.management_org,   # 3.1 机构职责
    'section_3_2': project.management.management_policy, # 3.2 目标方针（+ energy_management 制度句合并）
    'section_3_3': project.management.honors,           # 3.3 成效（+ es 成效/痛点合并）
    'section_3_4': <es 改造措施生成>,                     # 3.4 有数据才有该键
    'images': [{'path': ..., 'caption': ...}, ...],      # 图片列表（可选）
}
```

> ⚠️ **已无 `config.chapter_texts` 机制**：`chapter_texts` 仅存在于 `rag/energy_audit_importer.py`（知识库导入器），`report_generator.py` 不消费。第3章文本一律从 `project.management` + `project.energy_saving` 组装；author 要覆盖某节，直接改 `report_data['chapter3'][key]`。

---

## 数据来源（字段速查）

- 3.1 机构职责：`proj.management.management_org`（采集阶段 `enrich_management_info` 由制度文件 LLM 提炼）；为空按 `proj.base.institution_category` 选模板。
- 3.2 目标方针：`proj.management.management_policy`（目标+方针合并段）；`es.energy_management`（1=有制度，0=无制度，None=未填写）判定的制度句在 `management_policy` 为空时叠加。`management_goals` 当前未消费。
- 3.3 成效/问题：`proj.management.honors`；`es.has_awards` / `es.award_name` / `es.energy_pain_points`。
- 3.4 改造：`es.lighting_replacement` / `ac_replacement` / `water_saving_fixture_replacement` / `central_ac_control` / `other_measures` / `third_party_system` / `charging_pile` / `charging_settlement` / `charging_installation` / `third_party_outsource` / `outsource_content` / `outsource_settlement`。
- 制度文件图片：`es.management_file_images` + `es.award_certificate_images`（本地路径，采集阶段已下载）；`proj.images[]` 分类 `'管理文件/荣誉'`。
- 最新一条节能管理信息：`es = max((e for e in proj.energy_saving if e), key=lambda e: e.statistical_year or 0, default=None)`。
- `management_files` 存的是**文件 ID 串**（逗号分隔，供 `file_resolver` 解析下载），**不是可直接引用的路径，勿当路径用**。
- 管理机构名称、负责人、方针文件名称：用户提供。

---

## 常见错误

| 错误 | 后果 | 正确做法 |
|---|---|---|
| 只写 3.1/3.2/3.3，漏 3.4 | `build_chapter3` 有 4 节，3.4 改造措施缺失 | 凡 es 有改造字段，必须写 3.4 |
| 用 `config.chapter_texts` 传第3章文本 | 不被消费，静默丢失 | 用 `report_data['chapter3']` 覆盖 |
| 引用旧编排 `agent_xiaocheng` / `search_for_chapter` 仿写 | 已废弃 | 用 `energy_audit_imitate_paragraph` 工具 / `/api/energy-audit/imitate` |
| 把 `management_files`（文件ID串）当本地路径 | 图片缺失/路径错误 | 用 `management_file_images` 本地路径；ID 串只供 `file_resolver` |
| 3.2 只取 `management_policy`，忽略 `energy_management` 制度句 | 管理制度有无未表述 | 空时叠加 `_energy_saving_chapter3_sections` 的制度句 |
| 3.3 编造荣誉/问题 | 报告含虚假数据 | 只用 `honors` / `has_awards` / `award_name` / `energy_pain_points` 实际字段 |
| 3.4 扩写未记录的改造措施 | 与数据矛盾 | 只用 es 各改造字段展开 |
