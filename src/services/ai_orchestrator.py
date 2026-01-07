import asyncio
import json
import time
from typing import List, Dict, Any
from src.utils.groq_client import client
from src.services.usage_service import log_usage, check_model_usage_today

sem = asyncio.Semaphore(10)

# Mantendo sua config de modelos (ajuste conforme disponibilidade)
MODEL_CONFIG = {
    "extractor": "qwen/qwen3-32b",
    "architect": "llama-3.3-70b-versatile",
    "builders": {
        "iniciante": "meta-llama/llama-4-scout-17b-16e-instruct", 
        "intermediario": "meta-llama/llama-4-scout-17b-16e-instruct",
        "avancado": "meta-llama/llama-4-scout-17b-16e-instruct",
        "expert_primary": "llama-3.3-70b-versatile",
        "expert_economy": "meta-llama/llama-4-scout-17b-16e-instruct"
    },
    "fallback": "llama-3.1-8b-instant"
}

LANG_MAP = {
    "pt-br": "Portuguese (Brazil)",
    "en": "English",
    "es": "Spanish"
}

LIMIT_70B_TOKENS = 85000

async def extract_core_topic(user_input: str) -> str:
    """
    Transforma inputs como 'Quero aprender sobre X' em apenas 'X'.
    """
    print(f"🔍 [Extrator] Analisando intenção: '{user_input}'...")
    
    prompt = f"""
    Analyze the user input: "{user_input}".
    Extract the main educational topic/subject they want to study.
    Remove filler words like "I want to learn", "Help me with", "Create cards for".
    Keep it concise (1-5 words max).
    
    Output JSON ONLY: {{ "topic": "Extracted Topic Here" }}
    """
    
    start_time = time.time()
    model = MODEL_CONFIG["extractor"]
    
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.3 # Baixa temperatura para ser literal
        )
        
        # Log de Uso
        duration = time.time() - start_time
        if completion.usage:
            usage_data = {
                "prompt_tokens": completion.usage.prompt_tokens,
                "completion_tokens": completion.usage.completion_tokens,
                "total_tokens": completion.usage.total_tokens
            }
            log_usage(model, usage_data, duration, "intent-extractor")
            
        data = json.loads(completion.choices[0].message.content)
        cleaned_topic = data.get("topic", user_input)
        print(f"✅ [Extrator] Tópico identificado: '{cleaned_topic}'")
        return cleaned_topic

    except Exception as e:
        print(f"⚠️ Erro no Extrator: {e}. Usando input original.")
        return user_input

def resolve_model_for_level(level: str) -> str:
    """
    Decide qual modelo usar. Se for 'expert', verifica a cota do dia.
    """
    if level != "expert":
        return MODEL_CONFIG["builders"].get(level, MODEL_CONFIG["fallback"])
    
    # Lógica Especial para Expert
    primary_model = MODEL_CONFIG["builders"]["expert_primary"]
    
    # Verifica consumo atual no banco
    current_usage = check_model_usage_today(primary_model)
    
    if current_usage < LIMIT_70B_TOKENS:
        print(f"💎 Cota 70B OK ({current_usage}/85k). Usando Expert Premium.")
        return primary_model
    else:
        print(f"📉 Cota 70B Alta ({current_usage}/85k). Mudando Expert para Economia (Scout).")
        return MODEL_CONFIG["builders"]["expert_economy"]

# ---------------------------------------------------------
# 1. O ARQUITETO (Planejamento)
# ---------------------------------------------------------

async def plan_curriculum(topic: str, lang_code: str) -> Dict[str, List[str]]:
    start_time = time.time()
    target_language = LANG_MAP.get(lang_code.lower(), "English")
    print(f"🧠 [Arquiteto] Planejando estrutura para: {topic}...")
    
    # MUDANÇA 1: Aumentamos para 5 sub-tópicos por nível
    prompt = f"""
    You are an expert Professor. Create a structured flashcard curriculum for the topic: '{topic}'.
    The user wants to learn this in {target_language}.
    
    Divide into 4 difficulty levels: 'iniciante', 'intermediario', 'avancado', 'expert'.
    For EACH level, list exactly 5 specific sub-topics.
    
    Output strictly VALID JSON format like this:
    {{
      "iniciante": ["Subtopic A", "Subtopic B", ...],
      "intermediario": [...],
      ...
    }}
    """
    
    try:
        completion = client.chat.completions.create(
            model=MODEL_CONFIG["architect"],
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        duration = time.time() - start_time
        # O objeto usage vem dentro de completion.usage
        if completion.usage:
            # Precisamos converter o objeto Usage para dict ou acessar atributos
            usage_dict = {
                "prompt_tokens": completion.usage.prompt_tokens,
                "completion_tokens": completion.usage.completion_tokens,
                "total_tokens": completion.usage.total_tokens
            }
            log_usage(MODEL_CONFIG["architect"], usage_dict, duration, "architect")

        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        print(f"❌ Architect Error: {e}")
        duration = time.time() - start_time
        if completion.usage:
            usage_dict = {
                "prompt_tokens": completion.usage.prompt_tokens,
                "completion_tokens": completion.usage.completion_tokens,
                "total_tokens": completion.usage.total_tokens
            }
            log_usage(MODEL_CONFIG["fallback"], usage_dict, duration, f"builder-{level}-fallback")
        return {
            "iniciante": [f"{topic} Basics 1", f"{topic} Basics 2"],
            "intermediario": [f"{topic} Inter 1"],
            "avancado": [f"{topic} Adv 1"],
            "expert": [f"{topic} Exp 1"]
        }

# ---------------------------------------------------------
# 2. O CONSTRUTOR (Execução)
# ---------------------------------------------------------

async def generate_micro_batch(level: str, subtopic: str, lang_code: str) -> List[Dict[str, Any]]:
    target_language = LANG_MAP.get(lang_code.lower(), "English")
    target_model = resolve_model_for_level(level)
    
    # MUDANÇA 2: Aumentamos para 5 cards por sub-tópico
    # (5 tópicos * 5 cards = 25 cards por nível = 100 total)
    prompt = f"""
    Topic: {subtopic} (Difficulty: {level}).
    Target Language: {target_language}.
    
    Create exactly 5 high-quality educational flashcards.
    
    JSON Output Format:
    {{
      "cards": [
        {{ 
           "front": "Question/Term in {target_language}", 
           "back": "Answer/Definition in {target_language}" 
        }}
      ]
    }}
    """
    
    async with sem:
        start_time = time.time()
        used_model = target_model
        is_fallback = False
        
        try:
            completion = client.chat.completions.create(
                model=target_model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            content = json.loads(completion.choices[0].message.content)
            cards = content.get("cards", [])
            
            duration = time.time() - start_time
            if completion.usage:
                usage_dict = {
                    "prompt_tokens": completion.usage.prompt_tokens,
                    "completion_tokens": completion.usage.completion_tokens,
                    "total_tokens": completion.usage.total_tokens
                }
                log_usage(used_model, usage_dict, duration, f"builder-{level}")
            
            # Adiciona metadados
            for card in cards:
                card["generated_by_model"] = target_model
                card["quality_flag"] = "ok"
                # IMPORTANTE: Adicionamos o nível no card para agrupar depois
                card["level"] = level 
                
            return cards
        except Exception as e:
            print(f"⚠️ Builder Error ({target_model}): {e}")
            duration = time.time() - start_time
            if completion.usage:
                usage_dict = {
                    "prompt_tokens": completion.usage.prompt_tokens,
                    "completion_tokens": completion.usage.completion_tokens,
                    "total_tokens": completion.usage.total_tokens
                }
                log_usage(MODEL_CONFIG["fallback"], usage_dict, duration, f"builder-{level}-fallback")
            return []

# ---------------------------------------------------------
# 3. O ORQUESTRADOR (Agregação Estruturada)
# ---------------------------------------------------------

async def generate_full_deck_service(raw_input: str, language: str = "pt-br"):
    clean_topic = await extract_core_topic(raw_input)
    curriculum = await plan_curriculum(clean_topic, language)
    
    tasks = []
    
    # Cria as tarefas
    for level, subtopics in curriculum.items():
        for sub in subtopics:
            tasks.append(generate_micro_batch(level, sub, language))
            
    print(f"🚀 Disparando {len(tasks)} gerações paralelas...")
    
    # Executa tudo em paralelo
    results_lists = await asyncio.gather(*tasks)
    
    # Achata a lista de listas para processar
    all_flat_cards = [card for batch in results_lists for card in batch]
    
    # MUDANÇA 3: Lógica de Agrupamento por Nível
    # Inicializa a estrutura para garantir a ordem
    grouped_structure = {
        "iniciante": [],
        "intermediario": [],
        "avancado": [],
        "expert": []
    }
    
    # Distribui os cards nas caixinhas certas
    for card in all_flat_cards:
        lvl = card.get("level")
        if lvl and lvl in grouped_structure:
            # Removemos a chave 'level' de dentro do card se não quiser redundância, 
            # mas manter pode ser útil. Vamos manter.
            grouped_structure[lvl].append(card)
    
    # Monta a lista final no formato solicitado pelo Schema
    final_cards_list = []
    for level_name, cards_list in grouped_structure.items():
        final_cards_list.append({
            "level": level_name,
            "cards": cards_list
        })
    
    return {
        "topic": clean_topic, # Retorna o tópico limpo para o frontend exibir
        "original_input": raw_input,
        "language": language,
        "total_cards": len(all_flat_cards),
        "cards": final_cards_list # Agora segue a estrutura aninhada
    }