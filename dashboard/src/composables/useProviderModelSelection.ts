import { ref } from 'vue';

const SELECTED_PROVIDER_KEY = 'selectedProvider';
const SELECTED_PROVIDER_MODEL_KEY = 'selectedProviderModel';

// Module-level state so every ProviderModelMenu instance (header, input)
// shares the same selection.
const selectedProviderId = ref('');
const selectedModelName = ref('');
let syncedFromStorage = false;

/** Hydrate the shared selection once when the dashboard loads. */
function syncFromStorage() {
  if (syncedFromStorage || typeof window === 'undefined') return;
  syncedFromStorage = true;
  try {
    selectedProviderId.value =
      localStorage.getItem(SELECTED_PROVIDER_KEY) || '';
    selectedModelName.value =
      localStorage.getItem(SELECTED_PROVIDER_MODEL_KEY) || '';
  } catch {
    selectedProviderId.value = '';
    selectedModelName.value = '';
  }
}

/** Share provider/model selection state across chat selector instances. */
export function useProviderModelSelection() {
  syncFromStorage();

  /** Update the shared state and its browser persistence. */
  function setSelection(providerId: string, modelName = '') {
    selectedProviderId.value = providerId;
    selectedModelName.value = modelName;
    try {
      localStorage.setItem(SELECTED_PROVIDER_KEY, providerId);
      localStorage.setItem(SELECTED_PROVIDER_MODEL_KEY, modelName);
    } catch {
      // Selection persistence must not block the UI.
    }
  }

  return { selectedProviderId, selectedModelName, setSelection };
}
