"""Composition root for API version 1."""

from fastapi import APIRouter

from app.api import auth, system, users

router = APIRouter()
router.include_router(system.router)
router.include_router(auth.router)
router.include_router(users.router)
