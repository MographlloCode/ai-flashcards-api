from datetime import datetime, date, timedelta
from sqlmodel import Session, select, func
from src.db.session import engine
from src.models.usage_log import UsageLog

# Função simples para salvar log (abre e fecha sessão rapidinho)
def log_usage(model_id: str, usage_data: dict, time_taken: float, tag: str):
    if not usage_data:
        return

    with Session(engine) as session:
        log = UsageLog(
            model_id=model_id,
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
            time_taken_seconds=time_taken,
            context_tag=tag
        )
        session.add(log)
        session.commit()

# Função para relatório (usada na rota GET)
def get_daily_usage_stats():
    today = date.today()
    start_of_day = datetime.combine(today, datetime.min.time())
    
    with Session(engine) as session:
        # Agrupa por modelo para você saber qual está gastando mais
        statement = (
            select(
                UsageLog.model_id,
                func.count(UsageLog.id).label("request_count"),
                func.sum(UsageLog.total_tokens).label("total_tokens_sum"),
                func.sum(UsageLog.time_taken_seconds).label("total_time")
            )
            .where(UsageLog.timestamp >= start_of_day)
            .group_by(UsageLog.model_id)
        )
        
        results = session.exec(statement).all()
        
        stats = []
        grand_total_tokens = 0
        grand_total_requests = 0
        
        for row in results:
            model, reqs, tokens, time = row
            grand_total_tokens += tokens
            grand_total_requests += reqs
            
            stats.append({
                "model": model,
                "requests_today": reqs,
                "tokens_today": tokens,
                "avg_latency": round(time / reqs, 2) if reqs > 0 else 0
            })
            
        return {
            "date": str(today),
            "summary": {
                "total_requests": grand_total_requests,
                "total_tokens": grand_total_tokens
            },
            "by_model": stats
        }
        
def check_model_usage_today(model_id: str) -> int:
    """
    Retorna o total de tokens consumidos por um modelo específico HOJE.
    """
    today = date.today()
    start_of_day = datetime.combine(today, datetime.min.time())
    
    with Session(engine) as session:
        statement = (
            select(func.sum(UsageLog.total_tokens))
            .where(UsageLog.model_id == model_id)
            .where(UsageLog.timestamp >= start_of_day)
        )
        total = session.exec(statement).one()
        return total if total else 0