import network
import time
import ujson
from machine import Pin, ADC
from umqtt.simple import MQTTClient

# ---------------------------------------------------------
# 1. MAPEAMENTO DE HARDWARE E SENSORES (Borda)
# ---------------------------------------------------------
pino_pir = Pin(13, Pin.IN)          # Sensor de Presença (Digital)
pino_ldr = ADC(Pin(34))             # Sensor de Luminosidade LDR (Analógico)
pino_ldr.atten(ADC.ATTN_11DB)       # Configura leitura para faixa de 0 a 3.3V (0 - 4095)
pino_rele = Pin(2, Pin.OUT)         # Atuador: Relé/LED da iluminação
pino_rele.value(0)                  # Inicia com as luzes desligadas

# Limiar de luminosidade: abaixo deste valor, considera-se ambiente escuro
LIMIAR_LUZ = 1800  

# Estado e Modo de Operação
modo_operacao = "AUTOMATICO"        # Pode ser "AUTOMATICO" ou "MANUAL"
estado_lampada = "DESLIGADA"

# ---------------------------------------------------------
# 2. CONFIGURAÇÕES DE REDE E BROKER MQTT
# ---------------------------------------------------------
WIFI_SSID = "Wokwi-GUEST"          # Rede virtual padrão fornecida pelo Wokwi
WIFI_PASSWORD = ""
MQTT_BROKER = "broker.hivemq.com"  # Broker público utilizado nos testes
MQTT_PORT = 1883
MQTT_CLIENT_ID = "esp32-sala101-ads-unifor"

# Tópicos definidos no Percurso 2
TOPICO_DADOS = "universidade/predioA/sala101/dados"
TOPICO_COMANDO = "universidade/predioA/sala101/comando"

# ---------------------------------------------------------
# 3. CONEXÃO WI-FI
# ---------------------------------------------------------
def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Conectando ao Wi-Fi Wokwi...", end="")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        while not wlan.isconnected():
            time.sleep(0.2)
            print(".", end="")
    print("\n[Wi-Fi] Conectado com sucesso! IP:", wlan.ifconfig())

# ---------------------------------------------------------
# 4. TRATAMENTO DE COMANDOS REMOTOS (Callback MQTT)
# ---------------------------------------------------------
def callback_mqtt(topic, msg):
    global modo_operacao, estado_lampada
    topico_str = topic.decode('utf-8')
    mensagem_str = msg.decode('utf-8').strip()
    print(f"\n[MQTT Comando] Mensagem recebida em '{topico_str}': {mensagem_str}")
    
    try:
        # Interpreta como JSON ou comando direto (ON / OFF / AUTO)
        if mensagem_str.startswith("{"):
            comando_obj = ujson.loads(mensagem_str)
            acao = comando_obj.get("acao", "").upper()
        else:
            acao = mensagem_str.upper()
            
        if acao == "ON":
            modo_operacao = "MANUAL"
            pino_rele.value(1)
            estado_lampada = "LIGADA"
            print(">> Lâmpada ligada MANUALMENTE via comando.")
        elif acao == "OFF":
            modo_operacao = "MANUAL"
            pino_rele.value(0)
            estado_lampada = "DESLIGADA"
            print(">> Lâmpada desligada MANUALMENTE via comando.")
        elif acao == "AUTO":
            modo_operacao = "AUTOMATICO"
            print(">> Retornando ao modo AUTOMÁTICO de detecção local.")
    except Exception as erro:
        print("[MQTT Erro] Falha ao processar comando:", erro)

# ---------------------------------------------------------
# 5. CONEXÃO COM O BROKER MQTT
# ---------------------------------------------------------
def conectar_mqtt():
    cliente = MQTTClient(MQTT_CLIENT_ID, MQTT_BROKER, port=MQTT_PORT)
    cliente.set_callback(callback_mqtt)
    try:
        print("Conectando ao Broker MQTT...", end="")
        cliente.connect()
        cliente.subscribe(TOPICO_COMANDO)
        print(" Conectado!")
        print(f"Inscrito com sucesso no canal de comandos: {TOPICO_COMANDO}")
        return cliente
    except Exception as erro:
        print(f"\n[Erro MQTT] Falha de conexão: {erro}")
        return None

# ---------------------------------------------------------
# 6. LOOP PRINCIPAL DE EXECUÇÃO
# ---------------------------------------------------------
conectar_wifi()
cliente_mqtt = conectar_mqtt()

ultimo_envio = time.time()
INTERVALO_ENVIO = 5  # Envia telemetria a cada 5 segundos

print("\n--- Sistema de Iluminação IoT Inicializado ---")

while True:
    try:
        # Verifica periodicamente se chegaram comandos remotos
        if cliente_mqtt:
            cliente_mqtt.check_msg()
            
        tempo_atual = time.time()
        
        # Leitura dos Sensores (Fase 3)
        presenca = pino_pir.value()              # Retorna 1 (movimento) ou 0 (sem movimento)
        leitura_luz = pino_ldr.read()            # Retorna valor entre 0 e 4095
        
        # Ação sobre o Atuador / Regra de Automação (Fase 5)
        if modo_operacao == "AUTOMATICO":
            # SE há presença na sala E a luz ambiente está baixa, LIGA
            if presenca == 1 and leitura_luz < LIMIAR_LUZ:
                pino_rele.value(1)
                estado_lampada = "LIGADA"
            else:
                pino_rele.value(0)
                estado_lampada = "DESLIGADA"

        # Publicação de Telemetria via MQTT (Fase 4)
        if tempo_atual - ultimo_envio >= INTERVALO_ENVIO:
            payload = {
                "sala_id": "sala-101",
                "presenca": presenca,
                "luminosidade": leitura_luz,
                "rele_lampada": estado_lampada,
                "modo": modo_operacao
            }
            mensagem_json = ujson.dumps(payload)
            
            if cliente_mqtt:
                cliente_mqtt.publish(TOPICO_DADOS, mensagem_json)
                print(f"[Telemetria Enviada]: {mensagem_json}")
            
            ultimo_envio = tempo_atual
            
        time.sleep(0.1)  # Pequena pausa para estabilidade do ciclo
        
    except OSError as e:
        print("[Aviso] Conexão oscilou. Tentando reconectar...")
        time.sleep(2)
        try:
            cliente_mqtt = conectar_mqtt()
        except:
            pass
