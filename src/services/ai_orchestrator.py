import asyncio
import json
import time
from typing import List, Dict, Any
from src.utils.groq_client import client
# Importamos os serviços de log e verificação de cota
from src.services.usage_service import log_usage, check_model_usage_today

sem = asyncio.Semaphore(10) # Controla conexões simultâneas
LIMIT_70B_TOKENS = 85000 

# --- CONFIGURAÇÃO DE ALTA PERFORMANCE (ATUALIZADA) ---

MODEL_CONFIG = {
    # Extrator Rápido (usa quase nada de output tokens)
    "extractor": "llama-3.1-8b-instant",

    # Arquiteto (usa pouco output, pois gera apenas a lista de tópicos)
    "architect": "llama-3.3-70b-versatile",

    "builders": {
        # MUDANÇA CRÍTICA: Trocamos Qwen (6k TPM) por Scout (30k TPM)
        # Isso multiplica sua capacidade de atendimento por 5x no nível iniciante
        # e evita o erro 429 quando vários usuários acessam ao mesmo tempo.
        "iniciante": "meta-llama/llama-4-scout-17b-16e-instruct", 
        
        "intermediario": "meta-llama/llama-4-scout-17b-16e-instruct",
        "avancado": "meta-llama/llama-4-scout-17b-16e-instruct",
        
        # Expert: Continua com a lógica Smart (70B -> Scout se acabar a cota)
        "expert_primary": "llama-3.3-70b-versatile",
        "expert_economy": "meta-llama/llama-4-scout-17b-16e-instruct"
    },
    
    # Fallback "Tanque de Guerra" (Limite quase infinito)
    "fallback": "llama-3.1-8b-instant"
}

LANG_MAP = {
    "pt-br": "Portuguese (Brazil)",
    "en": "English",
    "es": "Spanish"
}

# ---------------------------------------------------------
# 0. O EXTRATOR (Analisa a intenção do usuário)
# ---------------------------------------------------------

async def extract_core_topic(user_input: str) -> str:
    print(f"🔍 [Extrator] Analisando: '{user_input}'...")
    prompt = f"""
    Analyze the user input: "{user_input}".
    Extract the main educational topic/subject.
    Remove filler words. Keep it concise (1-5 words).
    Output JSON ONLY: {{ "topic": "Extracted Topic" }}
    """
    start_time = time.time()
    try:
        completion = client.chat.completions.create(
            model=MODEL_CONFIG["extractor"],
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        # Log de uso simplificado
        if completion.usage:
             usage_dict = {
                "prompt_tokens": completion.usage.prompt_tokens,
                "completion_tokens": completion.usage.completion_tokens,
                "total_tokens": completion.usage.total_tokens
            }
             log_usage(MODEL_CONFIG["extractor"], usage_dict, time.time() - start_time, "intent")
        
        data = json.loads(completion.choices[0].message.content)
        return data.get("topic", user_input)
    except:
        return user_input

# ---------------------------------------------------------
# 1. O ARQUITETO (Planejamento)
# ---------------------------------------------------------

async def plan_curriculum(topic: str, lang_code: str) -> Dict[str, List[str]]:
    target_language = LANG_MAP.get(lang_code.lower(), "English")
    print(f"🧠 [Arquiteto] Planejando estrutura para: {topic}...")
    
    prompt = f"""
    You are an expert Professor. Create a structured flashcard curriculum for: '{topic}'.
    Target Language: {target_language}.
    
    Divide into 4 levels: 'iniciante', 'intermediario', 'avancado', 'expert'.
    For EACH level, list exactly 5 specific sub-topics.
    Output strictly VALID JSON.
    """
    
    start_time = time.time()
    try:
        completion = client.chat.completions.create(
            model=MODEL_CONFIG["architect"],
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        if completion.usage:
             usage_dict = {
                "prompt_tokens": completion.usage.prompt_tokens,
                "completion_tokens": completion.usage.completion_tokens,
                "total_tokens": completion.usage.total_tokens
            }
             log_usage(MODEL_CONFIG["architect"], usage_dict, time.time() - start_time, "architect")
        
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        print(f"❌ Architect Error: {e}")
        # Fallback de estrutura
        return {k: [f"{topic} {k} concept"] for k in ["iniciante", "intermediario", "avancado", "expert"]}

# ---------------------------------------------------------
# 2. RESOLUÇÃO DE MODELO (Smart Throttling)
# ---------------------------------------------------------

def resolve_model_for_level(level: str) -> str:
    # Se não for expert, pega o definido no config (agora Scout para todos os básicos)
    if level != "expert":
        return MODEL_CONFIG["builders"].get(level, MODEL_CONFIG["fallback"])
    
    # Lógica Smart para Expert
    primary = MODEL_CONFIG["builders"]["expert_primary"]
    usage = check_model_usage_today(primary)
    
    if usage < LIMIT_70B_TOKENS:
        return primary
    return MODEL_CONFIG["builders"]["expert_economy"]

# ---------------------------------------------------------
# 3. O CONSTRUTOR (Com Retry Inteligente)
# ---------------------------------------------------------

async def generate_micro_batch(level: str, subtopic: str, lang_code: str) -> List[Dict[str, Any]]:
    target_language = LANG_MAP.get(lang_code.lower(), "English")
    target_model = resolve_model_for_level(level)
    
    prompt = f"""
    Topic: {subtopic} (Difficulty: {level}).
    Target Language: {target_language}.
    Create exactly 5 high-quality flashcards.
    JSON Output Format: {{ "cards": [{{ "front": "...", "back": "..." }}] }}
    """
    
    async with sem:
        start_time = time.time()
        used_model = target_model
        is_fallback = False
        
        # --- NOVO: Loop de Retry para Resiliência ---
        for attempt in range(2): 
            try:
                completion = client.chat.completions.create(
                    model=target_model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                content_str = completion.choices[0].message.content
                
                # Log de sucesso
                if completion.usage:
                    usage_dict = {
                        "prompt_tokens": completion.usage.prompt_tokens,
                        "completion_tokens": completion.usage.completion_tokens,
                        "total_tokens": completion.usage.total_tokens
                    }
                    log_usage(used_model, usage_dict, time.time() - start_time, f"builder-{level}")
                
                # Se deu certo, sai do loop e processa
                break 
                
            except Exception as e:
                # Se for a primeira tentativa e for erro de Rate Limit (429), espera um pouco
                if "429" in str(e) and attempt == 0:
                    print(f"⏳ Rate Limit no {target_model}. Esperando 2s antes de tentar de novo...")
                    await asyncio.sleep(2)
                    continue
                
                # Se falhar na segunda vez ou for outro erro, ativa o Fallback
                print(f"⚠️ Falha no {target_model}: {e}. Indo para fallback...")
                used_model = MODEL_CONFIG["fallback"]
                is_fallback = True
                
                try:
                    completion = client.chat.completions.create(
                        model=used_model,
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"}
                    )
                    content_str = completion.choices[0].message.content
                    break # Sai do loop se o fallback funcionar
                except:
                    return [] # Se até o fallback falhar, retorna vazio

        # Processamento do JSON
        try:
            data = json.loads(content_str)
            cards = data.get("cards", [])
            for card in cards:
                card["generated_by_model"] = used_model
                card["level"] = level
                # Marca needs_review apenas se caiu no modelo 8B (fallback de erro)
                card["quality_flag"] = "needs_review" if "8b-instant" in used_model else "ok"
            return cards
        except:
            return []

# ---------------------------------------------------------
# 4. O ORQUESTRADOR
# ---------------------------------------------------------

async def generate_full_deck_service(raw_input: str, language: str = "pt-br"):
    # 1. Extração da Intenção
    clean_topic = await extract_core_topic(raw_input)
    
    # 2. Planejamento do Currículo
    curriculum = await plan_curriculum(clean_topic, language)
    
    tasks = []
    # 3. Criação das Tarefas
    for level, subtopics in curriculum.items():
        for sub in subtopics:
            tasks.append(generate_micro_batch(level, sub, language))
            
    print(f"🚀 Disparando {len(tasks)} gerações paralelas para '{clean_topic}'...")
    results_lists = await asyncio.gather(*tasks)
    
    all_flat_cards = [card for batch in results_lists for card in batch]
    
    # 4. Agrupamento Final por Nível
    grouped = {k: [] for k in ["iniciante", "intermediario", "avancado", "expert"]}
    for c in all_flat_cards:
        if c.get("level") in grouped:
            grouped[c["level"]].append(c)
            
    # Remove níveis vazios e formata para o Schema
    final_cards_list = [{"level": k, "cards": v} for k, v in grouped.items() if v]

    return {
        "topic": clean_topic,
        "original_input": raw_input,
        "language": language,
        "total_cards": len(all_flat_cards),
        "cards": final_cards_list
    }