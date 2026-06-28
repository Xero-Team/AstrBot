<template>
  <div class="message-parts-renderer">
    <template
      v-for="(part, partIndex) in parts"
      :key="partKey(part, partIndex)"
    >
      <div
        v-if="part.type === 'reply'"
        class="reply-quote"
        @click="openReply(part)"
      >
        <v-icon size="small" class="reply-quote-icon">mdi-reply</v-icon>
        <span class="reply-quote-text">{{
          part.selected_text || `#${part.message_id || ''}`
        }}</span>
      </div>

      <pre
        v-else-if="part.type === 'plain' && part.text"
        class="plain-content"
        >{{ part.text }}</pre
      >

      <div
        v-else-if="part.type === 'image' && imageUrl(part)"
        class="image-attachments"
      >
        <div class="image-attachment">
          <img
            :src="imageUrl(part)"
            class="attached-image"
            @click="$emit('open-image-preview', imageUrl(part))"
          />
        </div>
      </div>

      <div
        v-else-if="part.type === 'record' && mediaUrl(part)"
        class="audio-attachment"
      >
        <audio controls class="audio-player">
          <source :src="mediaUrl(part)" :type="part.mime_type || 'audio/wav'" />
        </audio>
      </div>

      <div
        v-else-if="part.type === 'video' && mediaUrl(part)"
        class="video-attachment"
      >
        <video controls class="video-player">
          <source :src="mediaUrl(part)" :type="part.mime_type || 'video/mp4'" />
        </video>
      </div>

      <div
        v-else-if="part.type === 'file' && filePayload(part)"
        class="file-attachments"
      >
        <div class="file-attachment">
          <a
            v-if="filePayload(part).url"
            :href="filePayload(part).url"
            :download="filePayload(part).filename"
            class="file-link"
            :class="{ 'is-dark': isDark }"
          >
            <v-icon size="small" class="file-icon"
              >mdi-file-document-outline</v-icon
            >
            <span class="file-name">{{ filePayload(part).filename }}</span>
          </a>
          <a
            v-else
            class="file-link file-link-download"
            :class="{ 'is-dark': isDark }"
            @click.prevent="$emit('download-file', filePayload(part))"
          >
            <v-icon size="small" class="file-icon"
              >mdi-file-document-outline</v-icon
            >
            <span class="file-name">{{ filePayload(part).filename }}</span>
            <v-icon
              v-if="isDownloading(filePayload(part).attachment_id)"
              size="small"
              class="download-icon"
              >mdi-loading mdi-spin</v-icon
            >
            <v-icon v-else size="small" class="download-icon"
              >mdi-download</v-icon
            >
          </a>
        </div>
      </div>

      <div v-else-if="part.type === 'tool_call'" class="tool-call-block">
        <template
          v-for="tool in part.tool_calls || []"
          :key="tool.id || tool.name || JSON.stringify(tool)"
        >
          <IPythonToolBlock
            v-if="isPythonTool(tool)"
            :tool-call="tool"
            :is-dark="isDark"
          />
          <ToolCallCard v-else :tool-call="tool" :is-dark="isDark" />
        </template>
      </div>

      <MarkdownMessagePart
        v-else-if="part.type === 'markdown' && part.text"
        :content="part.text"
        :refs="null"
        :is-dark="isDark"
        :custom-html-tags="[]"
      />

      <div v-else-if="part.text" class="plain-content">{{ part.text }}</div>
    </template>
  </div>
</template>

<script setup>
import IPythonToolBlock from './IPythonToolBlock.vue';
import MarkdownMessagePart from './MarkdownMessagePart.vue';
import ToolCallCard from './ToolCallCard.vue';

const props = defineProps({
  parts: {
    type: Array,
    default: () => [],
  },
  isDark: {
    type: Boolean,
    default: false,
  },
  currentTime: {
    type: Number,
    default: 0,
  },
  downloadingFiles: {
    type: Object,
    default: () => new Set(),
  },
});

defineEmits(['open-image-preview', 'download-file']);

const mediaUrl = (part) =>
  part?.embedded_url || part?.url || part?.file_url || part?.path || '';

const imageUrl = (part) => mediaUrl(part);

const filePayload = (part) => part?.embedded_file || part?.file || null;

const isDownloading = (attachmentId) =>
  Boolean(attachmentId) && props.downloadingFiles?.has?.(attachmentId);

const partKey = (part, index) =>
  [
    part?.type || 'unknown',
    part?.message_id || '',
    part?.attachment_id || '',
    part?.filename || '',
    index,
  ].join(':');

const isPythonTool = (tool) =>
  ['astrbot_execute_ipython', 'astrbot_execute_python'].includes(
    String(tool?.name || ''),
  );

const openReply = (part) => {
  if (!part?.message_id) return;
  const element = document.getElementById(`message-${part.message_id}`);
  element?.scrollIntoView({ behavior: 'smooth', block: 'center' });
};
</script>
