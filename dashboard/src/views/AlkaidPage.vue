<template>
  <v-card style="height: 100%; width: 100%">
    <v-card-text class="pa-4" style="height: 100%">
      <v-container fluid class="d-flex flex-column" style="height: 100%">
        <div style="margin-bottom: 32px">
          <h1 class="gradient-text">{{ tm('page.title') }}</h1>
          <small style="color: #a3a3a3">{{ tm('page.subtitle') }}</small>
        </div>

        <div
          style="display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap"
        >
          <v-btn
            size="large"
            :variant="isActive('knowledge-base') ? 'flat' : 'tonal'"
            :color="isActive('knowledge-base') ? '#9b72cb' : ''"
            rounded="lg"
            @click="navigateTo('knowledge-base')"
          >
            <v-icon start>mdi-text-box-search</v-icon>
            {{ tm('page.navigation.knowledgeBase') }}
          </v-btn>
          <v-btn
            size="large"
            :variant="isActive('long-term-memory') ? 'flat' : 'tonal'"
            :color="isActive('long-term-memory') ? '#9b72cb' : ''"
            rounded="lg"
            @click="navigateTo('long-term-memory')"
          >
            <v-icon start>mdi-dots-hexagon</v-icon>
            {{ tm('page.navigation.longTermMemory') }}
          </v-btn>
          <v-btn
            size="large"
            :variant="isActive('other') ? 'flat' : 'tonal'"
            :color="isActive('other') ? '#9b72cb' : ''"
            rounded="lg"
            @click="navigateTo('other')"
          >
            <v-icon start>mdi-tools</v-icon>
            {{ tm('page.navigation.other') }}
          </v-btn>
        </div>

        <div id="sub-view" class="flex-grow-1" style="max-height: 100%">
          <router-view></router-view>
        </div>
      </v-container>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useModuleI18n } from '@/i18n/composables';

type AlkaidTab = 'knowledge-base' | 'long-term-memory' | 'other';

const { tm } = useModuleI18n('features/alkaid/index');
const route = useRoute();
const router = useRouter();

function navigateTo(tab: AlkaidTab) {
  try {
    void router.push(`/alkaid/${tab}`);
  } catch (error) {
    console.warn('Navigation error:', error);
  }
}

function isActive(tab: AlkaidTab) {
  try {
    return route.path.includes(`/alkaid/${tab}`);
  } catch (error) {
    console.warn('Route check error:', error);
    return false;
  }
}

onMounted(() => {
  if (route.path === '/alkaid') {
    navigateTo('knowledge-base');
  }
});
</script>

<style scoped>
.gradient-text {
  background: linear-gradient(
    74deg,
    #2abfe1 0,
    #9b72cb 25%,
    #b55908 50%,
    #d93025 100%
  );

  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  font-weight: bold;
}

#subview {
  display: flex;
  flex-direction: column;
  flex-grow: 1;
  width: 100%;
  height: 100%;
}
</style>
