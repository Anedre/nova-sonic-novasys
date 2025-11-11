document.addEventListener('DOMContentLoaded', () => {
    const socket = io();
    let mediaRecorder;
    let audioChunks = [];
    let isRecording = false;
    let totalTokens = 0;
    let totalCost = 0;

    // Elementos DOM
    const callButton = document.getElementById('callButton');
    const transcript = document.getElementById('transcript');
    const promptSelect = document.getElementById('prompt-select');
    const debugContent = document.getElementById('debugContent');
    const debugPanel = document.getElementById('debugPanel');
    const debugToggle = document.getElementById('debugToggle');
    const debugClose = document.getElementById('debugClose');
    const tokenInfo = document.getElementById('tokenInfo');
    const costInfo = document.getElementById('costInfo');
    const callStatus = document.getElementById('callStatus');
    const avatarCircle = document.getElementById('avatarCircle');

    // Configuración del audio
    const audioConfig = {
        audio: {
            channelCount: 1,
            sampleRate: 16000,
            echoCancellation: true,
            noiseSuppression: true
        }
    };

    // Función para agregar mensajes al debugger
    function addDebugMessage(message) {
        const debugMsg = document.createElement('div');
        const timestamp = new Date().toLocaleTimeString('es-PE', { 
            hour: '2-digit', 
            minute: '2-digit', 
            second: '2-digit',
            fractionalSecondDigits: 3
        });
        const msgText = typeof message === 'object' ? JSON.stringify(message, null, 2) : message;
        debugMsg.textContent = `[${timestamp}] ${msgText}`;
        debugContent.appendChild(debugMsg);
        debugContent.scrollTop = debugContent.scrollHeight;
    }

    // Función para agregar transcripción
    function addTranscript(text, isUser = false) {
        const item = document.createElement('div');
        item.className = `transcript-item ${isUser ? 'transcript-user' : 'transcript-agent'}`;
        item.textContent = text;
        transcript.appendChild(item);
        transcript.scrollTop = transcript.scrollHeight;
    }

    // Función para actualizar métricas
    function updateMetrics(tokens, cost) {
        totalTokens += tokens;
        totalCost += cost;
        tokenInfo.textContent = `${totalTokens} tokens`;
        costInfo.textContent = `$${totalCost.toFixed(4)}`;
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

    // Inicializar grabación de audio
    async function initializeAudio() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia(audioConfig);
            mediaRecorder = new MediaRecorder(stream);

            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    audioChunks.push(event.data);
                }
            };

            mediaRecorder.onstop = async () => {
                if (audioChunks.length === 0) {
                    addDebugMessage('No hay datos de audio para enviar');
                    return;
                }

                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                const reader = new FileReader();
                
                reader.onload = () => {
                    const base64Audio = reader.result.split(',')[1];
                    socket.emit('audio_data', {
                        audio: base64Audio,
                        timestamp: new Date().toISOString(),
                        size: audioBlob.size
                    });
                    addDebugMessage(`Audio enviado: ${(audioBlob.size / 1024).toFixed(2)} KB`);
                };

                reader.readAsDataURL(audioBlob);
                audioChunks = [];
            };

            callButton.disabled = false;
            updateCallStatus('Conectado - Lista para hablar', false);
            addDebugMessage('Audio inicializado correctamente');
        } catch (error) {
            updateCallStatus('Error de micrófono', false);
            addDebugMessage({ error: 'Error al inicializar audio: ' + error.message });
            callButton.disabled = true;
        }
    }

    // Event Listeners para el botón de llamada
    callButton.addEventListener('mousedown', startRecording);
    callButton.addEventListener('mouseup', stopRecording);
    callButton.addEventListener('touchstart', (e) => {
        e.preventDefault();
        startRecording();
    });
    callButton.addEventListener('touchend', (e) => {
        e.preventDefault();
        stopRecording();
    });

    function startRecording() {
        if (!mediaRecorder || callButton.disabled) {
            addDebugMessage({ error: 'MediaRecorder no está listo' });
            return;
        }

        isRecording = true;
        callButton.classList.add('recording');
        audioChunks = [];
        mediaRecorder.start();
        updateCallStatus('Escuchando...', true);
        addDebugMessage('Grabación iniciada');
    }

    function stopRecording() {
        if (!isRecording) return;
        
        isRecording = false;
        callButton.classList.remove('recording');
        mediaRecorder.stop();
        updateCallStatus('Procesando...', false);
        addDebugMessage('Grabación detenida');
    }

    // Toggle debug panel
    debugToggle.addEventListener('click', () => {
        debugPanel.classList.remove('hidden');
        debugPanel.classList.add('active');
    });

    debugClose.addEventListener('click', () => {
        debugPanel.classList.remove('active');
        setTimeout(() => {
            debugPanel.classList.add('hidden');
        }, 300);
    });

    // Cambio de prompt
    promptSelect.addEventListener('change', () => {
        const selectedPrompt = promptSelect.value;
        socket.emit('prompt_select', { prompt: selectedPrompt });
        addDebugMessage(`Prompt cambiado a: ${selectedPrompt}`);
        updateCallStatus('Reconfigurando...', false);
    });

    // Socket.io event handlers
    socket.on('connect', () => {
        addDebugMessage('Conexión WebSocket establecida');
        updateCallStatus('Inicializando...', false);
        initializeAudio();
    });

    socket.on('disconnect', () => {
        addDebugMessage('Desconectado del servidor');
        updateCallStatus('Desconectado', false);
        callButton.disabled = true;
    });

    socket.on('debug', (data) => {
        addDebugMessage(data);
    });

    socket.on('user_transcript', (data) => {
        addTranscript(data.text, true);
        addDebugMessage(`Transcripción usuario: ${data.text}`);
    });

    socket.on('nova_response', (data) => {
        addTranscript(data.text, false);
        updateMetrics(data.tokens || 0, data.cost || 0);
        updateCallStatus('Conectado - Lista para hablar', false);
        addDebugMessage(`Respuesta recibida - Tokens: ${data.tokens}, Costo: $${data.cost}`);
    });

    socket.on('nova_speaking', () => {
        updateCallStatus('Zhenia está hablando...', true);
        addDebugMessage('Nova Sonic generando respuesta');
    });

    socket.on('audio_playback', (data) => {
        // Aquí se podría reproducir el audio de respuesta de Nova Sonic
        addDebugMessage('Audio de respuesta recibido');
    });

    socket.on('connect_error', (error) => {
        addDebugMessage({ error: 'Error de conexión: ' + error.message });
        updateCallStatus('Error de conexión', false);
    });

    socket.on('error', (data) => {
        addDebugMessage({ error: data.message });
        updateCallStatus('Error', false);
    });

    // Prevenir zoom en iOS al hacer tap
    document.addEventListener('touchstart', (e) => {
        if (e.touches.length > 1) {
            e.preventDefault();
        }
    }, { passive: false });

    // Log inicial
    addDebugMessage('Aplicación iniciada');
    addDebugMessage(`User Agent: ${navigator.userAgent}`);
});