/**
 * undoStore.ts — 撤销/重做系统
 *
 * 栈式存储，记录每次模块变更的 snapshot（深拷贝 modules 数组）。
 * MAX_DEPTH = 50，超出淘汰最早记录。
 */

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { Module } from '../types/script';

const MAX_DEPTH = 50;

function cloneModules(modules: Module[]): Module[] {
  return JSON.parse(JSON.stringify(modules));
}

export const useUndoStore = defineStore('undo', () => {
  const undoStack = ref<Module[][]>([]);
  const redoStack = ref<Module[][]>([]);

  const canUndo = computed(() => undoStack.value.length > 0);
  const canRedo = computed(() => redoStack.value.length > 0);

  /** Push current state onto undo stack before making changes */
  function snapshot(modules: Module[]) {
    undoStack.value.push(cloneModules(modules));
    if (undoStack.value.length > MAX_DEPTH) {
      undoStack.value.shift();
    }
    // Clear redo on new action
    redoStack.value = [];
  }

  /** Undo: pop from undo stack, push current to redo */
  function undo(currentModules: Module[]): Module[] | null {
    if (undoStack.value.length === 0) return null;
    redoStack.value.push(cloneModules(currentModules));
    const prev = undoStack.value.pop()!;
    return prev;
  }

  /** Redo: pop from redo stack, push current to undo */
  function redo(currentModules: Module[]): Module[] | null {
    if (redoStack.value.length === 0) return null;
    undoStack.value.push(cloneModules(currentModules));
    const next = redoStack.value.pop()!;
    return next;
  }

  function clear() {
    undoStack.value = [];
    redoStack.value = [];
  }

  return { canUndo, canRedo, snapshot, undo, redo, clear };
});
