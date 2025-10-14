from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from app.db import teacher

router = APIRouter(prefix="/api/admin", tags=["admin"])


class TeacherAddRequest(BaseModel):
    user_id: str
    name: str
    email: str
    teacher_type: str  # 'teacher', 'school_nurse', 'counselor'


class TeacherBulkAddRequest(BaseModel):
    teachers: List[TeacherAddRequest]


class TeacherUpdateRequest(BaseModel):
    teacher_type: str


@router.get("/teachers")
async def get_teachers() -> Dict[str, Any]:
    """登録済み教師の全取得（タイプ別に分類）"""
    try:
        all_teachers = teacher.get_all_teachers()
        
        # タイプ別に分類
        teachers_by_type = {
            "teacher": [],
            "school_nurse": [],
            "counselor": []
        }
        
        for t in all_teachers:
            teacher_type = t.get("teacher_type", "teacher")
            if teacher_type in teachers_by_type:
                teachers_by_type[teacher_type].append(t)
        
        return {
            "success": True,
            "teachers": teachers_by_type
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/teachers/pending")
async def get_pending_teachers() -> Dict[str, Any]:
    """未登録の教師ユーザーを取得"""
    try:
        pending = teacher.get_pending_teachers()
        return {
            "success": True,
            "pending_teachers": pending
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/teachers/bulk-add")
async def bulk_add_teachers(request: TeacherBulkAddRequest) -> Dict[str, Any]:
    """教師を一括登録"""
    try:
        # バリデーション
        valid_types = ["teacher", "school_nurse", "counselor"]
        for t in request.teachers:
            if t.teacher_type not in valid_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid teacher_type: {t.teacher_type}"
                )
        
        # 登録実行
        teachers_data = [t.dict() for t in request.teachers]
        count = teacher.add_teachers(teachers_data)
        
        return {
            "success": True,
            "added_count": count,
            "message": f"{count}名の教師を登録しました"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/teachers/{user_id}/type")
async def update_teacher_type(user_id: str, request: TeacherUpdateRequest) -> Dict[str, Any]:
    """教師タイプの更新"""
    try:
        valid_types = ["teacher", "school_nurse", "counselor"]
        if request.teacher_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid teacher_type: {request.teacher_type}"
            )
        
        success = teacher.update_teacher_type(user_id, request.teacher_type)
        
        if not success:
            raise HTTPException(status_code=404, detail="教師が見つかりません")
        
        return {
            "success": True,
            "message": "教師タイプを更新しました"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/teachers/{user_id}")
async def delete_teacher(user_id: str) -> Dict[str, Any]:
    """教師の削除"""
    try:
        success = teacher.delete_teacher(user_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="教師が見つかりません")
        
        return {
            "success": True,
            "message": "教師を削除しました"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))