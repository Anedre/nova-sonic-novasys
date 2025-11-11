document.addEventListener('DOMContentLoaded', () => {
    const socket = io({
        transports: ['websocket', 'polling'],
        upgrade: true,
        reconnectionAttempts: 5,
        reconnectionDelay: 1000,
        timeout: 10000,
        forceNew: true
    });
    let mediaRecorder;
    let isCallActive = false;
    let totalTokens = 0;
    let totalCost = 0;
    let audioContext;
    let playbackCursor = 0;
    let selectedVoice = 'es-ES-Female';
    const getNow = () => (typeof performance !== 'undefined' && performance.now ? performance.now() : Date.now());
    const MAX_DEBUG_MESSAGES = 350;
    let outboundAudioBytesBuffer = 0;
    let outboundAudioLogAt = 0;
    let inboundAudioLogAt = 0;
    let inboundAudioChunkCounter = 0;
    let playbackChunkLogAt = 0;
    let lastAudioTimelineAt = 0;
    let playbackCompleteLogAt = 0;
    // OPTIMIZACIÓN: Reducido de 1000ms a 250ms para menor latencia
    // Chunks más pequeños = audio llega más rápido al modelo
    const CAPTURE_SLICE_MS = 250; // 250ms (4 chunks/segundo)
    
    // Forzar OGG/Opus que es mucho más confiable para streaming que WebM
    const PREFERRED_MIME_TYPES = [
        'audio/ogg;codecs=opus',
        'audio/webm;codecs=opus',
        'audio/webm'
    ];
    
    // Validación completa de MediaRecorder con mensaje al usuario
    let recorderMimeType = '';
    let mediaRecorderSupported = false;
    
    if (typeof MediaRecorder === 'undefined') {
        console.error('❌ MediaRecorder no disponible en este navegador');
    } else if (typeof MediaRecorder.isTypeSupported !== 'function') {
        console.warn('⚠️ MediaRecorder.isTypeSupported no disponible');
        recorderMimeType = 'audio/webm;codecs=opus'; // Fallback
        mediaRecorderSupported = true;
    } else {
        // Primero intentar OGG que es más robusto
        if (MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')) {
            recorderMimeType = 'audio/ogg;codecs=opus';
            mediaRecorderSupported = true;
        } else {
            recorderMimeType = PREFERRED_MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type)) || '';
            if (recorderMimeType) {
                mediaRecorderSupported = true;
            }
        }
    }
    
    if (!recorderMimeType) {
        recorderMimeType = 'audio/webm;codecs=opus'; // Fallback final
    }

    // Elementos DOM
    const callButton = document.getElementById('callButton');
    const transcript = document.getElementById('transcript');
    const promptSelect = document.getElementById('prompt-select');
    const voiceSelect = document.getElementById('voice-select');
    const debugContent = document.getElementById('debugContent');
    const debugPanel = document.getElementById('debugPanel');
    const debugToggle = document.getElementById('debugToggle');
    const debugClose = document.getElementById('debugClose');
    const tokenInfo = document.getElementById('tokenInfo');
    const costInfo = document.getElementById('costInfo');
    const callStatus = document.getElementById('callStatus');
    const avatarCircle = document.getElementById('avatarCircle');
    const callHint = document.getElementById('callHint');
    
    // Array para almacenar todos los mensajes de debug
    let debugMessages = [];
    const streamHealth = document.getElementById('streamHealth');
    const latencyBadge = document.getElementById('latencyBadge');
    const micLevelFill = document.getElementById('micLevelFill');
    const sessionDurationLabel = document.getElementById('sessionDurationLabel');
    const sessionTimeline = document.getElementById('sessionTimeline');
    const exportTranscriptButton = document.getElementById('exportTranscriptButton');
    const resetTranscriptButton = document.getElementById('resetTranscriptButton');
    const copyLeadButton = document.getElementById('copyLeadButton');
    const leadFieldsList = document.getElementById('leadFieldsList');
    const leadEmptyState = document.getElementById('leadEmptyState');
    const leadProgressBar = document.getElementById('leadProgressBar');
    const leadProgressLabel = document.getElementById('leadProgressLabel');
    const callerNameEl = document.querySelector('.caller-name');

    // Mapeo de nombres del bot por prompt
    const BOT_NAMES = {
        'udep_original': 'Zhenia',
        'euromotors': 'Mayra',
        'v8_minimal': 'Zhenia',
        'v7_conversational': 'Zhenia',
        'v6_structured': 'Zhenia',
        'simple_test': 'Zhenia'
    };

    // Mapeo de temas por prompt
    const THEME_MAP = {
        'udep_original': 'udep',
        'udep_compact': 'udep',
        'udep_v6_tool_use': 'udep',
        'udep_v6_1_motivacional': 'udep',
        'udep_v6_2_validacion_tel': 'udep',
        'udep_v6_3_optimizado': 'udep',
        'udep_v7_conversational': 'udep',
        'udep_v8_minimal': 'udep',
        'v8_minimal': 'udep',
        'v7_conversational': 'udep',
        'v6_structured': 'udep',
        'euromotors': 'euromotors',
        'test': 'test',
        'test_corto': 'test',
        'simple_test': 'test'
    };

    function getAgentName() {
        try {
            const key = (promptSelect && promptSelect.value) || 'udep_original';
            return BOT_NAMES[key] || 'Zhenia';
        } catch { return 'Zhenia'; }
    }

    function updateTheme() {
        try {
            const selectedPrompt = (promptSelect && promptSelect.value) || 'udep_original';
            const theme = THEME_MAP[selectedPrompt] || 'udep';
            document.body.dataset.theme = theme;
            console.log(`🎨 Theme: ${theme} (prompt: ${selectedPrompt})`);
        } catch (err) {
            console.warn('Error updating theme:', err);
            document.body.dataset.theme = 'udep';
        }
    }

    function updateBotDisplayName(fromPromptValue) {
        try {
            const key = fromPromptValue || (promptSelect && promptSelect.value) || 'udep_original';
            const displayName = BOT_NAMES[key] || 'Zhenia';
            if (callerNameEl) {
                callerNameEl.textContent = displayName;
            }
        } catch { /* noop */ }
    }

    // Inicializar tema y nombre al cargar
    updateTheme();
    updateBotDisplayName();

    // Cambiar tema y nombre al cambiar de prompt
    if (promptSelect) {
        promptSelect.addEventListener('change', () => {
            updateTheme();
            updateBotDisplayName(promptSelect.value);
        });
    }

    // Configuración del audio
    const audioConfig = {
        audio: {
            channelCount: 1,
            sampleRate: 16000,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true
        }
    };

    const leadFieldConfig = [
        { key: 'nombre_completo', label: 'Nombre' },
        { key: 'dni', label: 'DNI' },
        { key: 'telefono', label: 'Teléfono' },
        { key: 'email', label: 'Email' },
        { key: 'programa_interes', label: 'Programa' },
        { key: 'modalidad_preferida', label: 'Modalidad' },
        { key: 'horario_preferido', label: 'Horario' },
        { key: 'consentimiento', label: 'Consentimiento' },
    ];

    const conversationLog = [];
    let latestLead = null;
    let callStartTime = null;
    let durationTimer = null;
    let micContext = null;
    let micAnalyser = null;
    let micDataArray = null;
    let lastUserSpeechAt = null;
    let appendedAgentTimeline = false; // Evita duplicar el aviso de agente
    let metricsUpdateTimer = null;  // Timer para debounce de métricas

    // Función para agregar mensajes al debugger
    function addDebugMessage(message) {
        const timestamp = new Date().toLocaleTimeString('es-PE', { 
            hour: '2-digit', 
            minute: '2-digit', 
            second: '2-digit',
            fractionalSecondDigits: 3
        });
        const msgText = typeof message === 'object' ? JSON.stringify(message, null, 2) : message;
        
        // Detectar tipo de mensaje por contenido
        let messageType = 'info';
        if (msgText.includes('❌') || msgText.includes('Error') || msgText.includes('error') || msgText.includes('fatal')) {
            messageType = 'error';
        } else if (msgText.includes('⚠️') || msgText.includes('Warning') || msgText.includes('warning')) {
            messageType = 'warning';
        } else if (msgText.includes('✅') || msgText.includes('éxito') || msgText.includes('completado') || msgText.includes('Conectado')) {
            messageType = 'success';
        }
        
        // Almacenar en array
        debugMessages.push({
            timestamp,
            message: msgText,
            type: messageType
        });
        
        // Crear elemento
        const debugMsg = document.createElement('div');
        debugMsg.className = `debug-entry ${messageType}`;
        debugMsg.textContent = `[${timestamp}] ${msgText}`;
        
        debugContent.appendChild(debugMsg);
        debugContent.scrollTop = debugContent.scrollHeight;
        while (debugContent.children.length > MAX_DEBUG_MESSAGES) {
            debugContent.removeChild(debugContent.firstChild);
        }
    }

    function setStreamHealth(label, tone = 'neutral') {
        if (!streamHealth) return;
        streamHealth.textContent = label;
        
        // Actualizar indicador visual
        const statusIndicator = document.getElementById('statusIndicator');
        if (statusIndicator) {
            statusIndicator.className = 'status-indicator';
            
            if (tone === 'positive') {
                statusIndicator.classList.add('active');
            } else if (tone === 'negative') {
                statusIndicator.classList.add('error');
            }
        }
    }

    function updateLatencyBadge(latencyMs) {
        const latencyBadge = document.getElementById('latencyBadge');
        const latencyBadgeContainer = document.getElementById('latencyBadgeContainer');
        
        if (!latencyBadge || !latencyBadgeContainer) return;
        
        // Formatear latencia
        let displayValue = latencyMs;
        if (latencyMs >= 1000) {
            displayValue = (latencyMs / 1000).toFixed(2) + 's';
            latencyBadge.nextElementSibling.textContent = '';
        } else {
            displayValue = Math.round(latencyMs);
            latencyBadge.nextElementSibling.textContent = 'ms';
        }
        
        latencyBadge.textContent = displayValue;
        
        // Aplicar clase según velocidad
        latencyBadgeContainer.classList.remove('fast', 'slow', 'critical');
        
        if (latencyMs < 500) {
            latencyBadgeContainer.classList.add('fast');
        } else if (latencyMs < 1500) {
            latencyBadgeContainer.classList.add('slow');
        } else {
            latencyBadgeContainer.classList.add('critical');
        }
    }

    function appendTimeline(message, tone = 'neutral') {
        if (!sessionTimeline) return;
        const item = document.createElement('li');
        item.className = `timeline-item ${tone}`;
        const time = document.createElement('span');
        time.className = 'timeline-time';
        time.textContent = new Date().toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' });
        const text = document.createElement('span');
        text.className = 'timeline-text';
        text.textContent = message;
        item.appendChild(time);
        item.appendChild(text);
        sessionTimeline.appendChild(item);
        while (sessionTimeline.children.length > 18) {
            sessionTimeline.removeChild(sessionTimeline.firstChild);
        }
        sessionTimeline.scrollTop = sessionTimeline.scrollHeight;
    }

    function formatDuration(ms) {
        if (!ms || ms < 0) return '00:00';
        const totalSeconds = Math.floor(ms / 1000);
        const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, '0');
        const seconds = String(totalSeconds % 60).padStart(2, '0');
        return `${minutes}:${seconds}`;
    }

    function updateSessionDuration() {
        if (!callStartTime) {
            sessionDurationLabel.textContent = '00:00';
            return;
        }
        const elapsed = Date.now() - callStartTime;
        sessionDurationLabel.textContent = formatDuration(elapsed);
    }

    function hasLeadData(lead) {
        if (!lead) return false;
        return leadFieldConfig.some(({ key }) => {
            const value = lead[key];
            return value !== null && value !== undefined && String(value).trim() !== '';
        });
    }

    function diffLead(newLead, oldLead) {
        if (!newLead) return [];
        if (!oldLead) {
            return leadFieldConfig
                .map((config) => (newLead[config.key] ? config.label : null))
                .filter(Boolean);
        }
        const changes = [];
        leadFieldConfig.forEach((config) => {
            const nextValue = newLead[config.key] ?? '';
            const prevValue = oldLead[config.key] ?? '';
            if (String(nextValue).trim() && nextValue !== prevValue) {
                changes.push(config.label);
            }
        });
        return changes;
    }

    function renderLeadPreview(lead) {
        leadFieldsList.innerHTML = '';
        const showData = hasLeadData(lead);
        leadEmptyState.style.display = showData ? 'none' : 'block';
        copyLeadButton.disabled = !showData;

        let completed = 0;
        leadFieldConfig.forEach(({ key, label }) => {
            const value = lead && lead[key] !== undefined ? lead[key] : '';
            const cleanValue = String(value || '').trim();
            const item = document.createElement('li');
            item.className = 'lead-item';

            const badge = document.createElement('span');
            badge.className = 'lead-label';
            badge.textContent = label;

            const content = document.createElement('span');
            content.className = 'lead-value';
            content.textContent = cleanValue || 'Pendiente';

            if (cleanValue) {
                item.classList.add('filled');
                completed += 1;
            }

            item.appendChild(badge);
            item.appendChild(content);
            leadFieldsList.appendChild(item);
        });

        const percent = leadFieldConfig.length
            ? Math.round((completed / leadFieldConfig.length) * 100)
            : 0;
        leadProgressBar.style.width = `${percent}%`;
        leadProgressLabel.textContent = `${percent}% completo`;
    }

    function setupMicVisualizer(stream) {
        if (!micLevelFill || typeof (window.AudioContext || window.webkitAudioContext) === 'undefined') {
            return;
        }
        if (!micContext) {
            micContext = new (window.AudioContext || window.webkitAudioContext)();
        }
        const source = micContext.createMediaStreamSource(stream);
        micAnalyser = micContext.createAnalyser();
        micAnalyser.fftSize = 512;
        source.connect(micAnalyser);
        micDataArray = new Uint8Array(micAnalyser.frequencyBinCount);

        const animate = () => {
            if (!micAnalyser) return;
            micAnalyser.getByteTimeDomainData(micDataArray);
            let peak = 0;
            for (let i = 0; i < micDataArray.length; i++) {
                const deviation = Math.abs(micDataArray[i] - 128) / 128;
                if (deviation > peak) {
                    peak = deviation;
                }
            }
            const level = Math.min(1, peak * 1.7);
            micLevelFill.style.transform = `scaleX(${level})`;
            micLevelFill.style.opacity = level > 0.05 ? 1 : 0.2;
            requestAnimationFrame(animate);
        };

        animate();
    }

    // Función para agregar transcripción
    function addTranscript(text, isUser = false) {
        const item = document.createElement('div');
        item.className = `transcript-item ${isUser ? 'transcript-user' : 'transcript-agent'}`;

        const meta = document.createElement('div');
        meta.className = 'transcript-meta';
        const who = isUser ? 'Tú' : getAgentName();
        meta.textContent = `${who} • ${new Date().toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;

        const body = document.createElement('div');
        body.className = 'transcript-text';
        body.textContent = text;

        item.appendChild(meta);
        item.appendChild(body);

        transcript.appendChild(item);
        transcript.scrollTop = transcript.scrollHeight;

        conversationLog.push({
            role: isUser ? 'Usuario' : getAgentName(),
            text,
            at: new Date().toISOString(),
        });
        exportTranscriptButton.disabled = conversationLog.length === 0;
    }

    function resetMetrics() {
        totalTokens = 0;
        totalCost = 0;
        renderMetrics();
    }

    function renderMetrics() {
        // Animación al actualizar valores
        tokenInfo.style.animation = 'none';
        costInfo.style.animation = 'none';
        
        requestAnimationFrame(() => {
            tokenInfo.textContent = totalTokens.toLocaleString();
            costInfo.textContent = `$${totalCost.toFixed(4)}`;
            
            tokenInfo.style.animation = 'valueUpdate 0.5s ease-out';
            costInfo.style.animation = 'valueUpdate 0.5s ease-out';
        });
        
        // Actualizar barra de progreso de tokens (máximo 10k tokens)
        const tokenProgress = document.getElementById('tokenProgress');
        if (tokenProgress) {
            const percentage = Math.min((totalTokens / 10000) * 100, 100);
            tokenProgress.style.width = `${percentage}%`;
        }
    }

    // Función para actualizar métricas con payload flexible y debounce
    function updateUsageMetrics(payload = {}) {
        const input = payload.inputTokens ?? payload.inputTokenCount ?? 0;
        const output = payload.outputTokens ?? payload.outputTokenCount ?? 0;
        const speech = payload.speechTokens ?? 0;
        const totalPayload = payload.totalTokens ?? 0;
        const costPayload = payload.estimatedCostUsd ?? payload.costUsd ?? null;

        if (totalPayload > 0) {
            totalTokens = totalPayload;
        } else {
            const increment = input + output + speech;
            if (increment > 0) {
                totalTokens += increment;
            }
        }

        if (typeof costPayload === 'number') {
            totalCost = costPayload;
        } else if (typeof costPayload === 'string' && !Number.isNaN(Number(costPayload))) {
            totalCost = Number(costPayload);
        }

        // Debounce de 100ms para evitar flicker en la UI
        if (metricsUpdateTimer) {
            clearTimeout(metricsUpdateTimer);
        }
        metricsUpdateTimer = setTimeout(() => {
            renderMetrics();
            metricsUpdateTimer = null;
        }, 100);

        addDebugMessage(`📊 Uso | input: ${input} • output: ${output} • speech: ${speech}`);
        if (costPayload !== null) {
            addDebugMessage(`💰 Costo estimado: ${Number(costPayload).toFixed(4)} USD`);
        }
    }

    // Función para actualizar estado de llamada
    function updateCallStatus(status, isActive = false) {
        callStatus.textContent = status;
        if (isActive) {
            avatarCircle.classList.add('active');
        } else {
            avatarCircle.classList.remove('active');
        }
    }

    const PCM_SAMPLE_RATE = 24000; // Nova Sonic entrega PCM 16-bit a 24 kHz

    // Función para reproducir audio
    async function playAudioResponse(base64Audio) {
        if (!base64Audio) {
            return;
        }

        try {
            const binaryString = atob(base64Audio);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }

            if (!audioContext) {
                audioContext = new (window.AudioContext || window.webkitAudioContext)();
                playbackCursor = 0;
            }

            if (audioContext.state === 'suspended') {
                await audioContext.resume();
            }

            const frameCount = Math.floor(bytes.length / 2);
            if (frameCount === 0) {
                addDebugMessage({ error: 'Audio vacío recibido' });
                return;
            }

            const audioBuffer = audioContext.createBuffer(1, frameCount, PCM_SAMPLE_RATE);
            const channelData = audioBuffer.getChannelData(0);

            for (let i = 0; i < frameCount; i++) {
                const offset = i * 2;
                const sample = (bytes[offset + 1] << 8) | bytes[offset];
                const signedSample = sample >= 0x8000 ? sample - 0x10000 : sample;
                channelData[i] = signedSample / 32768;
            }

            const source = audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(audioContext.destination);

            source.onended = () => {
                const remaining = playbackCursor - audioContext.currentTime;
                const nowMs = getNow();
                if (remaining <= 0.05 && nowMs - playbackCompleteLogAt > 600) {
                    addDebugMessage('✅ Reproducción de audio completada');
                    updateCallStatus('En llamada - Escuchando...', true);
                    playbackCompleteLogAt = nowMs;
                }
            };

            const now = audioContext.currentTime;
            if (!Number.isFinite(playbackCursor) || playbackCursor < now) {
                playbackCursor = now;
            }

            const scheduledTime = playbackCursor;
            playbackCursor += audioBuffer.duration;

            source.start(scheduledTime);
            const chunkLogNow = getNow();
            if (audioBuffer.duration >= 0.25 || chunkLogNow - playbackChunkLogAt > 1000) {
                addDebugMessage(`🎵 Chunk PCM ${frameCount} frames (${(audioBuffer.duration * 1000).toFixed(1)} ms)`);
                playbackChunkLogAt = chunkLogNow;
            }
            updateCallStatus(`${getAgentName()} hablando...`, true);

        } catch (error) {
            addDebugMessage({ error: 'Error al reproducir audio: ' + error.message });
        }
    }

    // Función para enviar chunks de audio continuamente
    // Inicializar grabación de audio continua
    async function initializeAudio() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia(audioConfig);
            setupMicVisualizer(stream);
            appendTimeline('Micrófono habilitado', 'positive');
            setStreamHealth('Listo para conectar', 'neutral');
            
            // Función para crear y configurar un nuevo MediaRecorder
            function createRecorder() {
                const recorder = new MediaRecorder(stream, {
                    mimeType: recorderMimeType
                });

                recorder.ondataavailable = (event) => {
                    if (event.data.size > 0 && isCallActive) {
                        const reader = new FileReader();
                        reader.onload = () => {
                            const base64Audio = reader.result.split(',')[1];
                            
                            // DEBUG: Verificar si el blob tiene contenido real
                            if (event.data.size > 0 && !window._audioDebugLogged) {
                                // Leer los primeros bytes para verificar
                                const debugReader = new FileReader();
                                debugReader.onload = (e) => {
                                    const arr = new Uint8Array(e.target.result);
                                    const first32 = Array.from(arr.slice(0, 32)).map(b => b.toString(16).padStart(2, '0')).join('');
                                    const variance = arr.slice(0, 1024).reduce((sum, val) => {
                                        const mean = 128;
                                        return sum + Math.pow(val - mean, 2);
                                    }, 0) / Math.min(1024, arr.length);
                                    addDebugMessage(`🎤 Audio capturado: ${event.data.size} bytes, header=${first32.substring(0, 16)}, varianza=${variance.toFixed(2)}`);
                                    window._audioDebugLogged = true;
                                };
                                debugReader.readAsArrayBuffer(event.data);
                            }
                            
                            socket.emit('audio_stream', {
                                audio: base64Audio,
                                timestamp: new Date().toISOString(),
                                size: event.data.size,
                                voice: selectedVoice,
                                mime: recorder.mimeType
                            });
                        };
                        reader.readAsDataURL(event.data);

                        outboundAudioBytesBuffer += event.data.size;
                        const now = getNow();
                        if (now - outboundAudioLogAt > 900) {
                            addDebugMessage(`📤 Audio enviado: ${(outboundAudioBytesBuffer / 1024).toFixed(2)} KB`);
                            outboundAudioBytesBuffer = 0;
                            outboundAudioLogAt = now;
                        }
                    }
                };

                return recorder;
            }

            mediaRecorder = createRecorder();
            callButton.disabled = false;
            updateCallStatus('Lista para conectar', false);
            callHint.textContent = 'Presiona para iniciar llamada';
            addDebugMessage('✅ Micrófono inicializado correctamente');
            addDebugMessage(`Formato de captura: ${mediaRecorder.mimeType}`);
            addDebugMessage(`Configuración: ${audioConfig.audio.sampleRate}Hz, ${audioConfig.audio.channelCount} canal`);
        } catch (error) {
            updateCallStatus('Error de micrófono', false);
            addDebugMessage({ error: '❌ Error al acceder al micrófono: ' + error.message });
            callButton.disabled = true;
            setStreamHealth('Error de micrófono', 'negative');
            appendTimeline('Error al inicializar el micrófono', 'negative');
        }
    }

    // Toggle de llamada (conectar/desconectar)
    callButton.addEventListener('click', () => {
        if (!isCallActive) {
            startCall();
        } else {
            endCall();
        }
    });

    resetTranscriptButton.addEventListener('click', () => {
        resetConversation();
        appendTimeline('Transcripciones reiniciadas manualmente', 'subtle');
        addDebugMessage('🧹 Transcripciones reiniciadas por el usuario');
    });

    exportTranscriptButton.addEventListener('click', () => {
        if (!conversationLog.length) {
            return;
        }
        const lines = conversationLog.map((entry) => {
            const timestamp = new Date(entry.at).toLocaleTimeString('es-PE', {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
            });
            return `[${timestamp}] ${entry.role}: ${entry.text}`;
        });
        const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `nova-session-${new Date().toISOString().replace(/[:.]/g, '-')}.txt`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        addDebugMessage('📥 Conversación exportada como TXT');
        appendTimeline('Conversación exportada', 'positive');
    });

    copyLeadButton.addEventListener('click', async () => {
        if (!latestLead || !hasLeadData(latestLead)) {
            return;
        }
        const lines = leadFieldConfig.map(({ key, label }) => {
            const value = latestLead[key];
            const cleanValue = String(value || '').trim();
            return `${label}: ${cleanValue || 'Pendiente'}`;
        });
        const payload = lines.join('\n');
        try {
            await navigator.clipboard.writeText(payload);
            addDebugMessage('📋 Lead copiado al portapapeles');
            appendTimeline('Lead copiado al portapapeles', 'positive');
        } catch (error) {
            addDebugMessage({ error: 'No se pudo copiar el lead: ' + error.message });
        }
    });

    function resetConversation() {
        transcript.innerHTML = '';
        conversationLog.length = 0;
        exportTranscriptButton.disabled = true;
        resetMetrics();
        renderMetrics();
        if (audioContext) {
            playbackCursor = audioContext.currentTime;
        } else {
            playbackCursor = 0;
        }
        updateLatencyBadge(0);
        const latencyBadge = document.getElementById('latencyBadge');
        if (latencyBadge) latencyBadge.textContent = '--';
    }

    function startCall() {
        // Validación completa de MediaRecorder antes de iniciar
        if (typeof MediaRecorder === 'undefined') {
            alert('❌ Tu navegador no soporta grabación de audio.\n\nPor favor usa:\n- Chrome 49+\n- Edge 79+\n- Firefox 25+\n- Safari 14.1+');
            addDebugMessage({ error: 'MediaRecorder no disponible en este navegador' });
            return;
        }
        
        if (!mediaRecorderSupported || !recorderMimeType) {
            alert('⚠️ Tu navegador no soporta los códecs de audio necesarios (Opus).\n\nPor favor actualiza tu navegador o usa Chrome/Edge.');
            addDebugMessage({ error: `Códecs no soportados. Mime type: ${recorderMimeType}` });
            return;
        }
        
        if (!mediaRecorder || callButton.disabled) {
            addDebugMessage({ error: 'MediaRecorder no está listo' });
            return;
        }

        isCallActive = true;
        callButton.classList.add('recording');
        callButton.querySelector('.call-icon').textContent = '📞';
        callHint.textContent = 'Presiona para finalizar llamada';

        // Reset de flags de debug para nueva sesión
        window._audioDebugLogged = false;
        
        outboundAudioBytesBuffer = 0;
        outboundAudioLogAt = getNow();
        inboundAudioLogAt = getNow();
        inboundAudioChunkCounter = 0;
        playbackChunkLogAt = 0;
        lastAudioTimelineAt = 0;

        resetConversation();
        sessionTimeline.innerHTML = '';
        appendTimeline('Llamada iniciada', 'positive');
        // Mostrar el nombre del agente según el prompt activo
        try {
            const selPrompt = promptSelect.value;
            const agentName = (BOT_NAMES[selPrompt] || 'Zhenia');
            appendTimeline(`Agente: ${agentName}`, 'subtle');
            appendedAgentTimeline = true;
        } catch { /* noop */ }
        setStreamHealth('Streaming activo', 'positive');
        if (durationTimer) {
            clearInterval(durationTimer);
        }
        callStartTime = Date.now();
        updateSessionDuration();
        durationTimer = setInterval(updateSessionDuration, 1000);
        lastUserSpeechAt = null;
        
        // Notificar al servidor que la llamada ha iniciado
    const selectedPrompt = promptSelect.value;
        const selectedVoiceValue = voiceSelect.value;
        
        socket.emit('call_started', {
            timestamp: new Date().toISOString(),
            voice: selectedVoiceValue,
            prompt: selectedPrompt
        });
        
        // Iniciar el ciclo de grabación continua
        if (mediaRecorder.state === 'inactive') {
            try {
                mediaRecorder.start(CAPTURE_SLICE_MS);
            } catch (error) {
                addDebugMessage({ error: 'No se pudo iniciar la grabación: ' + error.message });
            }
        }
        
        updateCallStatus('En llamada - Conversación fluida', true);
        addDebugMessage('🎙️ Llamada iniciada - Micrófono abierto (conversación continua)');
        appendTimeline(`Prompt activo: ${selectedPrompt.toUpperCase()} · Voz ${selectedVoiceValue}`, 'subtle');
    }

    function endCall() {
        if (!isCallActive) return;
        
        isCallActive = false;
        callButton.classList.remove('recording');
        callButton.querySelector('.call-icon').textContent = '📞';
        callHint.textContent = 'Presiona para iniciar llamada';
        
        // Detener grabación (el onstop NO reiniciará porque isCallActive = false)
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
        }
        
        updateCallStatus('Llamada finalizada', false);
        avatarCircle.classList.remove('active');
        addDebugMessage('📴 Llamada terminada');
        appendTimeline('Llamada finalizada', 'neutral');
        setStreamHealth('Sesión finalizada', 'subtle');
    appendedAgentTimeline = false;
        // Congelar duración final junto al costo
        let finalDurationStr = '00:00';
        if (callStartTime) {
            const elapsed = Date.now() - callStartTime;
            finalDurationStr = formatDuration(elapsed);
        }
        if (durationTimer) {
            clearInterval(durationTimer);
            durationTimer = null;
        }
        // Mostrar la duración final SOLO en su etiqueta dedicada
        sessionDurationLabel.textContent = finalDurationStr;
        // Mantener el costo sin concatenar la duración (evitar duplicidad visual)
        try {
            costInfo.textContent = `$${totalCost.toFixed(4)}`;
        } catch { /* noop */ }
        callStartTime = null;
        lastUserSpeechAt = null;
        if (audioContext) {
            playbackCursor = audioContext.currentTime;
        } else {
            playbackCursor = 0;
        }
        
        // Notificar al servidor
        socket.emit('call_ended', {
            timestamp: new Date().toISOString()
        });
    }

    // Toggle debug panel
    debugToggle.addEventListener('click', () => {
        debugPanel.classList.remove('hidden');
        debugPanel.classList.add('active');
        addDebugMessage('Panel de debug abierto');
    });

    debugClose.addEventListener('click', () => {
        debugPanel.classList.remove('active');
        setTimeout(() => {
            debugPanel.classList.add('hidden');
        }, 300);
    });

    // ==================== Sistema de Debug Draggable ====================
    const debugHeader = document.getElementById('debugHeader');
    const debugFilter = document.getElementById('debugFilter');
    const debugCopy = document.getElementById('debugCopy');
    const debugClear = document.getElementById('debugClear');
    
    let isDragging = false;
    let dragStartX = 0;
    let dragStartY = 0;
    let panelStartX = 0;
    let panelStartY = 0;
    
    debugHeader.addEventListener('mousedown', (e) => {
        // Solo permitir drag si no se clickea en los botones/select
        if (e.target.closest('.debug-toolbar')) return;
        
        isDragging = true;
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        
        const rect = debugPanel.getBoundingClientRect();
        panelStartX = rect.left;
        panelStartY = rect.top;
        
        debugPanel.style.transition = 'none';
        document.body.style.cursor = 'move';
    });
    
    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        
        const deltaX = e.clientX - dragStartX;
        const deltaY = e.clientY - dragStartY;
        
        const newX = panelStartX + deltaX;
        const newY = panelStartY + deltaY;
        
        // Limitar dentro de la ventana
        const maxX = window.innerWidth - debugPanel.offsetWidth;
        const maxY = window.innerHeight - debugPanel.offsetHeight;
        
        debugPanel.style.left = `${Math.max(0, Math.min(newX, maxX))}px`;
        debugPanel.style.top = `${Math.max(0, Math.min(newY, maxY))}px`;
        debugPanel.style.right = 'auto';
    });
    
    document.addEventListener('mouseup', () => {
        if (isDragging) {
            isDragging = false;
            debugPanel.style.transition = '';
            document.body.style.cursor = '';
        }
    });
    
    // Filtrado de logs
    debugFilter.addEventListener('change', () => {
        const filterValue = debugFilter.value;
        const entries = debugContent.querySelectorAll('.debug-entry');
        
        entries.forEach((entry) => {
            if (filterValue === 'all') {
                entry.classList.remove('hidden');
            } else {
                if (entry.classList.contains(filterValue)) {
                    entry.classList.remove('hidden');
                } else {
                    entry.classList.add('hidden');
                }
            }
        });
    });
    
    // Copiar log completo
    debugCopy.addEventListener('click', async () => {
        const logText = debugMessages.map(m => `[${m.timestamp}] ${m.message}`).join('\n');
        
        try {
            await navigator.clipboard.writeText(logText);
            
            // Feedback visual
            debugCopy.textContent = '✅';
            setTimeout(() => {
                debugCopy.textContent = '📋';
            }, 1500);
        } catch (err) {
            console.error('Error copiando:', err);
            // Fallback: crear textarea temporal
            const textarea = document.createElement('textarea');
            textarea.value = logText;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            
            debugCopy.textContent = '✅';
            setTimeout(() => {
                debugCopy.textContent = '📋';
            }, 1500);
        }
    });
    
    // Limpiar consola
    debugClear.addEventListener('click', () => {
        debugMessages = [];
        debugContent.innerHTML = '<div class="debug-entry info">Debug console limpiada</div>';
    });

    // Cambio de prompt
    promptSelect.addEventListener('change', () => {
        const selectedPrompt = promptSelect.value;
        socket.emit('prompt_select', { prompt: selectedPrompt });
        addDebugMessage(`🔄 Prompt cambiado a: ${selectedPrompt}`);
        updateCallStatus('Reconfigurando...', false);
    });

    // Cambio de voz
    voiceSelect.addEventListener('change', () => {
        selectedVoice = voiceSelect.value;
        socket.emit('voice_select', { voice: selectedVoice });
        addDebugMessage(`🗣️ Voz cambiada a: ${selectedVoice}`);
    });

    // Socket.io event handlers
    socket.on('connect', () => {
        addDebugMessage('🔌 Conexión WebSocket establecida');
        addDebugMessage(`Session ID: ${socket.id}`);
        updateCallStatus('Inicializando...', false);
        appendTimeline('Conexión WebSocket establecida', 'positive');
        setStreamHealth('Inicializando...', 'subtle');
        initializeAudio();
    });

    socket.on('disconnect', () => {
        addDebugMessage('⚠️ Desconectado del servidor');
        updateCallStatus('Desconectado', false);
        callButton.disabled = true;
        if (isCallActive) {
            endCall();
        }
        appendTimeline('Conexión perdida', 'negative');
        setStreamHealth('Sin conexión', 'negative');
    });

    socket.on('debug', (data) => {
        const msg = data.message || JSON.stringify(data);
        addDebugMessage(`🔍 ${msg}`);
    });

    socket.on('call_ready', () => {
        updateCallStatus('Conversación lista', true);
        addDebugMessage('✅ Nova Sonic listo para escuchar');
        appendTimeline('Sesión lista con Nova Sonic', 'positive');
        setStreamHealth('Sesión lista', 'positive');
        callHint.textContent = 'Habla cuando quieras';
    });

    socket.on('user_transcript', (data) => {
        addTranscript(data.text, true);
        addDebugMessage(`👤 Usuario: ${data.text}`);
        updateCallStatus('Procesando...', true);
        appendTimeline('Usuario habló', 'neutral');
        setStreamHealth('Procesando audio', 'warning');
        lastUserSpeechAt = Date.now();
    });

    socket.on('nova_response', (data) => {
        addTranscript(data.text, false);
    updateCallStatus(`${getAgentName()} respondiendo...`, true);
        addDebugMessage(`🤖 Nova: ${data.text.substring(0, 80)}...`);
    appendTimeline(`Respuesta de ${getAgentName()}`, 'neutral');
        setStreamHealth('Respuesta generada', 'positive');
        if (lastUserSpeechAt) {
            const delta = Date.now() - lastUserSpeechAt;
            updateLatencyBadge(delta);
            lastUserSpeechAt = null;
        }
    });

    socket.on('nova_speaking', () => {
        updateCallStatus(`${getAgentName()} hablando...`, true);
        addDebugMessage('🗣️ Nova Sonic generando respuesta');
        setStreamHealth('Sintetizando audio', 'positive');
    });

    socket.on('audio_playback', (data) => {
        const now = getNow();
        inboundAudioChunkCounter += 1;
        if (now - inboundAudioLogAt > 600) {
            addDebugMessage(`🔊 Recibiendo audio (${inboundAudioChunkCounter} chunks)`);
            inboundAudioChunkCounter = 0;
            inboundAudioLogAt = now;
        }

        if (data.audio) {
            playAudioResponse(data.audio);
            if (Date.now() - lastAudioTimelineAt > 1500) {
                appendTimeline('Audio enviado al cliente', 'subtle');
                lastAudioTimelineAt = Date.now();
            }
        }
    });

    socket.on('usage_update', (payload) => {
        updateUsageMetrics(payload || {});
    });

    socket.on('stream_event', (event) => {
        if (!event || !event.type) return;
        
        switch (event.type) {
            case 'stream_reconnecting':
                const attemptInfo = `${event.attempt}/${event.maxAttempts}`;
                const reconnectMsg = `🔄 Reconectando (${attemptInfo}) en ${event.delaySeconds}s...`;
                addDebugMessage(reconnectMsg);
                updateCallStatus(reconnectMsg, false);
                setStreamHealth(`Reconectando ${attemptInfo}`, 'warning');
                appendTimeline(reconnectMsg, 'warning');
                break;
                
            case 'stream_reconnected':
                const successMsg = `✅ Reconexión exitosa (intento ${event.attempt})`;
                addDebugMessage(successMsg);
                updateCallStatus('En llamada', true);
                setStreamHealth('Activo', 'positive');
                appendTimeline(successMsg, 'positive');
                break;
                
            case 'stream_error':
                const errorMsg = event.fatal 
                    ? `💀 Error fatal: ${event.reason}`
                    : `⚠️ Error del stream: ${event.reason}`;
                addDebugMessage({ error: errorMsg });
                
                if (event.fatal) {
                    updateCallStatus('Error fatal', false);
                    setStreamHealth('Error fatal', 'negative');
                    appendTimeline('Error fatal del stream', 'negative');
                    
                    // Terminar la llamada automáticamente
                    if (isInCall) {
                        setTimeout(() => {
                            hangUp();
                        }, 2000);
                    }
                } else {
                    setStreamHealth('Error', 'negative');
                    appendTimeline('Error del stream', 'negative');
                }
                break;
        }
    });

    socket.on('connection_info', (data) => {
        addDebugMessage('📡 Información de conexión:');
        addDebugMessage(`  - Modelo: ${data.model || 'N/A'}`);
        addDebugMessage(`  - Region: ${data.region || 'N/A'}`);
        addDebugMessage(`  - Voice: ${data.voice || 'N/A'}`);
        // Actualizar el nombre del bot según el prompt confirmado por el backend (si viene)
        if (data && data.prompt) {
            updateBotDisplayName(data.prompt);
        }
        const info = data.model && data.region ? `${data.model} · ${data.region}` : 'Modelo no informado';
        appendTimeline(`Conectado a ${info}`, 'subtle');
    });

    socket.on('connect_error', (error) => {
        addDebugMessage({ error: '❌ Error de conexión: ' + error.message });
        updateCallStatus('Error de conexión', false);
        setStreamHealth('Error de conexión', 'negative');
        appendTimeline('Error de conexión', 'negative');
    });

    socket.on('error', (data) => {
        addDebugMessage({ error: '❌ ' + data.message });
        updateCallStatus('Error', false);
        setStreamHealth('Error', 'negative');
        appendTimeline('Error recibido del backend', 'negative');
    });

    socket.on('lead_snapshot', (payload = {}) => {
        const previousLead = latestLead;
        const lead = payload.lead || {};
        latestLead = lead;
        renderLeadPreview(lead);
        const updates = diffLead(lead, previousLead);
        if (updates.length) {
            appendTimeline(`Lead actualizado (${updates.join(', ')})`, 'positive');
        } else if (payload.reason === 'session_end') {
            appendTimeline('Lead listo para exportar', 'positive');
        }
    });

    socket.on('lead_exported', (summary = {}) => {
        if (summary.export_path) {
            addDebugMessage(`💾 Lead exportado en ${summary.export_path}`);
            appendTimeline('Lead exportado a archivo', 'positive');
        } else {
            appendTimeline('Sesión cerrada sin lead para exportar', 'subtle');
        }
    });

    // Prevenir zoom en iOS al hacer tap
    document.addEventListener('touchstart', (e) => {
        if (e.touches.length > 1) {
            e.preventDefault();
        }
    }, { passive: false });

    // Log inicial
    addDebugMessage('🚀 Aplicación iniciada');
    addDebugMessage(`📱 User Agent: ${navigator.userAgent}`);
    addDebugMessage(`🌐 Idioma: ${navigator.language}`);
    renderLeadPreview(latestLead);
    exportTranscriptButton.disabled = true;
    copyLeadButton.disabled = true;
    setStreamHealth('En espera', 'neutral');
    renderMetrics();
});
