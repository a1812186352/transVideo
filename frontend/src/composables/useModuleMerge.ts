/**
 * useModuleMerge.ts — 时间轴相邻重复模块自动合并
 *
 * 合并条件：连续两个模块 start_time / duration 相同，且 detail 的 JSON 序列化一致
 * 合并规则：保留前一个模块为主键，类型标签斜杠拼接，merged_types 记录参与合并的类型
 * 约束：纯 computed 层，不改动原始 timeline.modules
 */

import { computed, type Ref } from 'vue';
import type { Module, ModuleType } from '../types/script';

export interface MergedModule extends Module {
  /** 参与合并的所有模块原始数据（供点击展开查看完整参数） */
  mergedChildren: Module[];
  /** 参与合并的所有模块类型列表 */
  mergedTypes: ModuleType[];
}

function detailJson(mod: Module): string {
  return JSON.stringify((mod as any).detail ?? {});
}

/**
 * 类型 → 中文标签映射（与 TimelineBar.vue 同步）
 */
const TYPE_LABEL: Record<ModuleType, string> = {
  title: '开头',
  video_segment: '高潮',
  subtitle: '字幕',
  transition: '转场',
  audio: '音频',
  effect: '特效',
};

function typeLabel(t: ModuleType): string {
  return TYPE_LABEL[t] || t;
}

/**
 * 接收原始 modules 数组，返回合并后的渲染列表。
 */
export function useModuleMerge(modulesRef: Ref<Module[]>) {
  return computed(() => {
    const raw = modulesRef.value;
    if (!raw.length) return [];

    const result: MergedModule[] = [];

    for (let i = 0; i < raw.length; i++) {
      const current = raw[i];
      const next = raw[i + 1];

      // 检查合并条件
      if (
        next &&
        current.start_time === next.start_time &&
        current.duration === next.duration &&
        detailJson(current) === detailJson(next)
      ) {
        // 合并：保留 current 为主键，收集 mergedChildren + mergedTypes
        const merged: MergedModule = {
          ...current,
          mergedChildren: [current, next],
          mergedTypes: [current.type, next.type],
        };
        result.push(merged);
        i++; // 跳过被合并的 next
      } else {
        // 不合并
        result.push({ ...current, mergedChildren: [current], mergedTypes: [current.type] });
      }
    }

    return result;
  });
}

/**
 * 将 mergedTypes 渲染为合并后的题头字符串
 */
export function mergedTypeLabel(types: ModuleType[]): string {
  return types.map(t => typeLabel(t)).join(' / ');
}
