/**
 * keyboardShortcuts.ts — 全局键盘快捷键
 *
 * 绑定时机：页面加载后自动激活（onMounted 中注册 keydown 监听）
 * 卸载时自动清理（onUnmounted 中 removeEventListener）
 * 所有快捷键在 input/textarea 获得焦点时不触发
 */

import { onMounted, onUnmounted } from 'vue';
import { useTimelineStore } from '../stores/timelineStore';
import { usePlaybackStore } from '../stores/playbackStore';
import { useUndoStore } from '../stores/undoStore';

let clipboardModule: any = null;

export function useKeyboardShortcuts() {
  const timeline = useTimelineStore();
  const playback = usePlaybackStore();
  const undo = useUndoStore();

  function isEditable(el: HTMLElement): boolean {
    const tag = el.tagName.toLowerCase();
    return tag === 'input' || tag === 'textarea' || el.isContentEditable;
  }

  function onKeyDown(e: KeyboardEvent) {
    // 跳过输入框/文本域
    if (isEditable(e.target as HTMLElement)) return;

    const ctrl = e.ctrlKey || e.metaKey;

    switch (e.code) {
      // ── Delete / Backspace: 删除选中模块 ──
      case 'Delete':
      case 'Backspace': {
        if (!timeline.selectedModuleId) return;
        e.preventDefault();
        undo.snapshot(timeline.modules);
        timeline.removeModule(timeline.selectedModuleId);
        break;
      }

      // ── Ctrl+Z: 撤销 / Ctrl+Shift+Z: 重做 ──
      case 'KeyZ': {
        if (!ctrl) return;
        e.preventDefault();
        if (e.shiftKey) {
          // Ctrl+Shift+Z → 重做
          const next = undo.redo(timeline.modules);
          if (next) timeline.setModules(next);
        } else {
          // Ctrl+Z → 撤销
          const prev = undo.undo(timeline.modules);
          if (prev) timeline.setModules(prev);
        }
        break;
      }

      // ── Ctrl+Y: 重做 ──
      case 'KeyY': {
        if (!ctrl) return;
        e.preventDefault();
        const next = undo.redo(timeline.modules);
        if (next) timeline.setModules(next);
        break;
      }

      // ── Space: 播放/暂停 ──
      case 'Space': {
        e.preventDefault();
        if (playback.isPlaying) {
          playback.pause();
          // Also pause the video element
          const v = document.querySelector('.preview__video') as HTMLVideoElement | null;
          if (v) v.pause();
        } else {
          playback.play();
          const v = document.querySelector('.preview__video') as HTMLVideoElement | null;
          if (v) v.play();
        }
        break;
      }

      // ── ← / →: 逐帧步进 ──
      case 'ArrowLeft': {
        e.preventDefault();
        const t = Math.max(0, playback.currentTime - 1 / 30);
        playback.seekTo(t);
        const v = document.querySelector('.preview__video') as HTMLVideoElement | null;
        if (v) v.currentTime = t;
        break;
      }
      case 'ArrowRight': {
        e.preventDefault();
        const maxDur = (document.querySelector('.preview__video') as HTMLVideoElement | null)?.duration || 60;
        const t = Math.min(maxDur, playback.currentTime + 1 / 30);
        playback.seekTo(t);
        const v = document.querySelector('.preview__video') as HTMLVideoElement | null;
        if (v) v.currentTime = t;
        break;
      }

      // ── Ctrl+S: 保存占位 ──
      case 'KeyS': {
        if (!ctrl) return;
        e.preventDefault();
        // 占位：可扩展为触发持久化
        console.log('[Save] 项目保存触发（待接入后端）');
        break;
      }

      // ── Ctrl+C: 复制选中模块 ──
      case 'KeyC': {
        if (!ctrl) return;
        if (!timeline.selectedModuleId) return;
        e.preventDefault();
        const mod = timeline.modules.find(m => m.id === timeline.selectedModuleId);
        if (mod) {
          clipboardModule = JSON.parse(JSON.stringify(mod));
          clipboardModule.id = crypto.randomUUID(); // 新 ID 留待粘贴时使用
        }
        break;
      }

      // ── Ctrl+V: 粘贴模块 ──
      case 'KeyV': {
        if (!ctrl || !clipboardModule) return;
        e.preventDefault();
        undo.snapshot(timeline.modules);
        const newMod = { ...clipboardModule, id: crypto.randomUUID() };
        timeline.addModule(newMod);
        break;
      }
    }
  }

  onMounted(() => {
    window.addEventListener('keydown', onKeyDown);
  });

  onUnmounted(() => {
    window.removeEventListener('keydown', onKeyDown);
  });
}
