import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import { chatApi } from '@/api/v1';

export interface Conversation {
  cid: string;
  title: string;
  updated_at: number;
}

interface SessionRecord {
  session_id: string;
  display_name: string | null;
  updated_at: string;
}

function hasStatusCode(error: unknown, statusCode: number): boolean {
  if (!error || typeof error !== 'object') {
    return false;
  }
  const response = (error as { response?: { status?: number } }).response;
  return response?.status === statusCode;
}

export function useConversations(chatboxMode: boolean = false) {
  const router = useRouter();
  const conversations = ref<Conversation[]>([]);
  const selectedConversations = ref<string[]>([]);
  const currCid = ref('');
  const pendingCid = ref<string | null>(null);

  // 编辑标题相关
  const editTitleDialog = ref(false);
  const editingTitle = ref('');
  const editingCid = ref('');

  const getCurrentConversation = computed(() => {
    if (!currCid.value) return null;
    return conversations.value.find((c) => c.cid === currCid.value);
  });

  async function getConversations() {
    try {
      const response = await chatApi.listSessions();
      const data = Array.isArray(response.data.data)
        ? (response.data.data as SessionRecord[])
        : [];
      conversations.value = data.map((session) => ({
        cid: session.session_id,
        title: session.display_name || session.session_id,
        updated_at: Date.parse(session.updated_at || '') || 0,
      }));

      // 处理待加载的会话
      if (pendingCid.value) {
        const conversation = conversations.value.find(
          (c) => c.cid === pendingCid.value,
        );
        if (conversation) {
          selectedConversations.value = [pendingCid.value];
          pendingCid.value = null;
        }
      } else if (!currCid.value && conversations.value.length > 0) {
        // 默认选择第一个会话
        const firstConversation = conversations.value[0];
        selectedConversations.value = [firstConversation.cid];
      }
    } catch (err) {
      if (hasStatusCode(err, 401)) {
        void router.push('/auth/login?redirect=/chatbox');
      }
      console.error(err);
    }
  }

  async function newConversation() {
    try {
      const response = await chatApi.createSession();
      const cid = response.data.data.session_id;
      currCid.value = cid;

      // 更新 URL
      const basePath = chatboxMode ? '/chatbox' : '/chat';
      void router.push(`${basePath}/${cid}`);

      await getConversations();
      return cid;
    } catch (err) {
      console.error(err);
      throw err;
    }
  }

  async function deleteConversation(cid: string) {
    try {
      await chatApi.deleteSession(cid);
      await getConversations();
      currCid.value = '';
      selectedConversations.value = [];
    } catch (err) {
      console.error(err);
    }
  }

  function showEditTitleDialog(cid: string, title: string) {
    editingCid.value = cid;
    editingTitle.value = title || '';
    editTitleDialog.value = true;
  }

  async function saveTitle() {
    if (!editingCid.value) return;

    const trimmedTitle = editingTitle.value.trim();
    try {
      await chatApi.updateSession(editingCid.value, {
        display_name: trimmedTitle,
      });

      // 更新本地会话标题
      const conversation = conversations.value.find(
        (c) => c.cid === editingCid.value,
      );
      if (conversation) {
        conversation.title = trimmedTitle;
      }
      editTitleDialog.value = false;
    } catch (err) {
      console.error('重命名对话失败:', err);
    }
  }

  function updateConversationTitle(cid: string, title: string) {
    const conversation = conversations.value.find((c) => c.cid === cid);
    if (conversation) {
      conversation.title = title;
    }
  }

  function newChat(closeMobileSidebar?: () => void) {
    currCid.value = '';
    selectedConversations.value = [];

    const basePath = chatboxMode ? '/chatbox' : '/chat';
    void router.push(basePath);

    if (closeMobileSidebar) {
      closeMobileSidebar();
    }
  }

  return {
    conversations,
    selectedConversations,
    currCid,
    pendingCid,
    editTitleDialog,
    editingTitle,
    editingCid,
    getCurrentConversation,
    getConversations,
    newConversation,
    deleteConversation,
    showEditTitleDialog,
    saveTitle,
    updateConversationTitle,
    newChat,
  };
}
