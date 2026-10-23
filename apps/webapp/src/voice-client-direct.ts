import { unsupported } from './adapter'

// Keep provider credentials on the backend. The existing voice consumers fall
// back to authenticated relay HTTP/WebSocket APIs when direct config is null.
export type { DirectTtsConfig, DirectSttConfig, VoiceClientConfig } from '../../desktop/src/lib/voice-client-direct'
type NativeVoice = typeof import('../../desktop/src/lib/voice-client-direct')
export const fetchVoiceClientConfig: NativeVoice['fetchVoiceClientConfig'] = async () => null
export const fetchVoiceClientConfigFor: NativeVoice['fetchVoiceClientConfigFor'] = async () => null
export const directTtsConfig: NativeVoice['directTtsConfig'] = async () => null
export const transcribeAudioClientDirect: NativeVoice['transcribeAudioClientDirect'] = async () => null
export const synthesizeSpeechClientDirect: NativeVoice['synthesizeSpeechClientDirect'] = async () => unsupported('Client-direct voice providers')
