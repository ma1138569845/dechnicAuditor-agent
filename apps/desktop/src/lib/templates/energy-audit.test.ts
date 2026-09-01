import { describe, expect, it } from 'vitest'

import {
  ENERGY_AUDIT_IMITATE_SKILL,
  energyAuditImitateSkillPrompt,
  shouldShowEnergyAuditTemplates
} from './energy-audit'

describe('energyAuditImitateSkillPrompt', () => {
  it('invokes the bundled skill with unit and audit type', () => {
    expect(energyAuditImitateSkillPrompt('烟台经济技术开发区人民法院', '公共机构')).toBe(
      `/${ENERGY_AUDIT_IMITATE_SKILL} 请为「烟台经济技术开发区人民法院」按「公共机构」类型仿写一份能源审计报告。` +
        '使用该单位在数据库中的项目数据，优先检索同区县、地市、省份的同类参考报告，按该类型八章结构逐章仿写，并生成 Word 文件。'
    )
  })

  it('trims the unit name and defaults a blank type', () => {
    const prompt = energyAuditImitateSkillPrompt('  省立医院东院  ', '   ')

    expect(prompt.startsWith(`/${ENERGY_AUDIT_IMITATE_SKILL} `)).toBe(true)
    expect(prompt).toContain('「省立医院东院」')
    expect(prompt).toContain('「公共机构」')
  })
})

describe('shouldShowEnergyAuditTemplates', () => {
  it('shows chips for audit keywords', () => {
    expect(shouldShowEnergyAuditTemplates('请生成能源审计报告')).toBe(true)
  })

  it('hides chips for unrelated text', () => {
    expect(shouldShowEnergyAuditTemplates('hello')).toBe(false)
  })
})
