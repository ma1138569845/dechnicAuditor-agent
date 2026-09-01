/**
 * Skill-triggered composer template chips for energy audit reports.
 *
 * These templates are surfaced when the user is writing about energy audits.
 * Selecting a chip fills the composer with a structured prompt that the
 * agent's energy-audit workflow can pick up and execute end-to-end.
 */

export type EnergyAuditType = '公共机构' | '公共建筑' | '工业企业'

export interface EnergyAuditTemplate {
  /** Stable template identifier. */
  id: string
  /** Short label shown on the chip. */
  label: string
  /** One-line description shown in tooltip or expanded card. */
  description: string
  /** Prompt text inserted into the composer when the chip is clicked. */
  prompt: string
  /** The audit type passed to the energy-audit backend workflow. */
  auditType: EnergyAuditType
}

/** Slash command that loads the bundled energy-audit-imitate skill. */
export const ENERGY_AUDIT_IMITATE_SKILL = 'energy-audit-imitate'

/** Desktop 智能体任务: submit this into the current chat to invoke the skill. */
export function energyAuditImitateSkillPrompt(unitName: string, auditType: string): string {
  const name = unitName.trim()
  const type = auditType.trim() || '公共机构'

  return (
    `/${ENERGY_AUDIT_IMITATE_SKILL} 请为「${name}」按「${type}」类型仿写一份能源审计报告。` +
    '使用该单位在数据库中的项目数据，优先检索同区县、地市、省份的同类参考报告，按该类型八章结构逐章仿写，并生成 Word 文件。'
  )
}

/** Keywords that trigger the energy-audit template chips. */
export const ENERGY_AUDIT_TRIGGER_KEYWORDS: string[] = [
  '能源审计报告',
  '能源审计',
  '节能报告',
  '能耗审计',
  'energy audit report',
  'energy audit',
  '节能诊断',
  '能效评估'
]

export const ENERGY_AUDIT_TEMPLATES: EnergyAuditTemplate[] = [
  {
    id: 'public-institution-audit',
    label: '公共机构能源审计报告',
    description: '政府机关、事业单位等公共机构年度能源审计报告',
    auditType: '公共机构',
    prompt:
      '请帮我生成一份公共机构能源审计报告。报告应包含：\n' +
      '1. 审计项目概况（被审计单位、审计年度、审计依据）\n' +
      '2. 能源消费总量及结构分析\n' +
      '3. 主要耗能系统与设备分析\n' +
      '4. 能耗指标计算与对标分析\n' +
      '5. 节能潜力分析与节能改造建议\n' +
      '6. 审计结论\n' +
      '请先确认被审计单位名称和审计年度，然后调用能源审计工具生成符合《能源审计报告编写格式规范标准》的 Word 报告。'
  },
  {
    id: 'public-building-audit',
    label: '公共建筑能源审计报告',
    description: '商业建筑、办公大楼等公共建筑能源审计报告',
    auditType: '公共建筑',
    prompt:
      '请帮我生成一份公共建筑能源审计报告。报告应包含：\n' +
      '1. 建筑基本信息与用能系统概述\n' +
      '2. 暖通空调系统能耗分析\n' +
      '3. 照明与插座系统能耗分析\n' +
      '4. 电梯、给排水等其他用能系统分析\n' +
      '5. 建筑能耗指标与对标分析\n' +
      '6. 节能改造建议与效益分析\n' +
      '请先确认建筑名称、建筑面积和审计年度，然后调用能源审计工具生成 Word 报告。'
  },
  {
    id: 'industrial-audit',
    label: '工业企业能源审计报告',
    description: '工厂、生产线等工业企业深度能源审计报告',
    auditType: '工业企业',
    prompt:
      '请帮我生成一份工业企业能源审计报告。报告应包含：\n' +
      '1. 企业概况、主要产品与生产工艺\n' +
      '2. 能源购入、消费与平衡分析\n' +
      '3. 主要耗能工序与设备分析\n' +
      '4. 单位产品能耗与能效对标\n' +
      '5. 余热余压等能源回收利用情况\n' +
      '6. 节能技术改造方案与投资回收分析\n' +
      '请先确认企业名称、主要产品、审计年度，然后调用能源审计工具生成 Word 报告。'
  },
  {
    id: 'energy-audit-outline',
    label: '能源审计报告大纲',
    description: '仅生成报告结构大纲，不填充具体数据',
    auditType: '公共机构',
    prompt:
      '请帮我生成一份能源审计报告的详细大纲（Word 格式），包含完整的章节结构、各级标题和每部分应包含的核心内容要点。'
  }
]

/** Returns true when the composer text should trigger energy-audit templates. */
export function shouldShowEnergyAuditTemplates(text: string): boolean {
  const lower = text.trim().toLowerCase()
  if (!lower) {
    return false
  }
  return ENERGY_AUDIT_TRIGGER_KEYWORDS.some(kw => lower.includes(kw.toLowerCase()))
}
