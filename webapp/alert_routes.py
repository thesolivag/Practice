"""Authenticated manual-watch controls shared by Telegram, browser and extension."""
from fastapi import APIRouter, Body, Depends, HTTPException
import db
from slk import user_alerts


def router(require_user):
    routes=APIRouter()
    @routes.get('/api/alerts/schema')
    def alert_schema(user=Depends(require_user)):
        return user_alerts.schema()
    @routes.get('/api/alerts/quote')
    def alert_quote(pair:str,user=Depends(require_user)):
        import alert_quotes
        try:return alert_quotes.preview(pair)
        except ValueError as exc:raise HTTPException(422,str(exc)) from None
    @routes.get('/api/alerts')
    def list_alerts(user=Depends(require_user)):
        try:
            with user_alerts.Repository(db) as repo:return repo.list(user['id'])
        except Exception:raise HTTPException(503,'Alert storage unavailable') from None
    @routes.post('/api/alerts')
    def create_alert(body:dict=Body(...),user=Depends(require_user)):
        try:
            data=user_alerts.validate(body)
            with user_alerts.Repository(db) as repo:return repo.create(user['id'],data)
        except ValueError as exc:raise HTTPException(422,str(exc)) from None
        except Exception:raise HTTPException(503,'Alert storage unavailable; save not confirmed') from None
    @routes.post('/api/alerts/{alert_id}/cancel')
    def cancel_alert(alert_id:int,user=Depends(require_user)):
        try:
            with user_alerts.Repository(db) as repo:result=repo.cancel(user['id'],alert_id)
        except ValueError as exc:raise HTTPException(409,str(exc)) from None
        except Exception:raise HTTPException(503,'Alert storage unavailable') from None
        if result is None:raise HTTPException(404,'Alert not found')
        return {'ok':True,'id':alert_id}
    return routes
