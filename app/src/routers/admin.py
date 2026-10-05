from __future__ import annotations
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import List, Dict, Any
from src.db import teacher
from src.db.sqlite import query_all, execute, now_iso
from src.utils.deps import require_teacher

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


class StudentUpdateRequest(BaseModel):
    name: str = None
    grade: str = None


@router.get("/teachers", dependencies=[Depends(require_teacher)])
async def get_teachers() -> Dict[str, Any]:
    try:
        all_teachers = teacher.get_all_teachers()
        teachers_by_type: Dict[str, list] = {
            "teacher": [],
            "school_nurse": [],
            "counselor": [],
        }
        for t in all_teachers:
            teacher_type = t.get("teacher_type", "teacher")
            if teacher_type in teachers_by_type:
                teachers_by_type[teacher_type].append(t)
        return {"success": True, "teachers": teachers_by_type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/teachers/pending", dependencies=[Depends(require_teacher)])
async def get_pending_teachers() -> Dict[str, Any]:
    try:
        pending = teacher.get_pending_teachers()
        return {"success": True, "pending_teachers": pending}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/teachers/bulk-add", dependencies=[Depends(require_teacher)])
async def bulk_add_teachers(request: TeacherBulkAddRequest) -> Dict[str, Any]:
    try:
        valid_types = ["teacher", "school_nurse", "counselor"]
        for t in request.teachers:
            if t.teacher_type not in valid_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid teacher_type: {t.teacher_type}",
                )
        teachers_data = [t.model_dump() for t in request.teachers]
        count = teacher.add_teachers(teachers_data)
        return {"success": True, "added_count": count, "message": f"{count}名の教師を登録しました"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/teachers/{user_id}/type", dependencies=[Depends(require_teacher)])
async def update_teacher_type(user_id: str, request: TeacherUpdateRequest) -> Dict[str, Any]:
    try:
        valid_types = ["teacher", "school_nurse", "counselor"]
        if request.teacher_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid teacher_type: {request.teacher_type}",
            )
        success = teacher.update_teacher_type(user_id, request.teacher_type)
        if not success:
            raise HTTPException(status_code=404, detail="教師が見つかりません")
        return {"success": True, "message": "教師タイプを更新しました"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/teachers/{user_id}", dependencies=[Depends(require_teacher)])
async def delete_teacher(user_id: str) -> Dict[str, Any]:
    try:
        success = teacher.delete_teacher(user_id)
        if not success:
            raise HTTPException(status_code=404, detail="教師が見つかりません")
        return {"success": True, "message": "教師を削除しました"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/students", dependencies=[Depends(require_teacher)])
async def get_students() -> Dict[str, Any]:
    try:
        rows = query_all(
            """
            SELECT u.user_id, u.name, u.grade, g.email, u.created_at
            FROM users u
            LEFT JOIN google_accounts g ON u.user_id = g.user_id
            WHERE u.role = 'student'
            ORDER BY u.grade, u.name
            """
        )
        students = [
            {
                "user_id": r[0],
                "name": r[1],
                "grade": r[2],
                "email": r[3],
                "created_at": r[4],
            }
            for r in rows
        ]
        students_by_grade: Dict[str, list] = {}
        for student in students:
            grade = student.get("grade") or "未設定"
            students_by_grade.setdefault(grade, []).append(student)
        return {"success": True, "students": students, "students_by_grade": students_by_grade}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/students/{user_id}", dependencies=[Depends(require_teacher)])
async def delete_student(user_id: str) -> Dict[str, Any]:
    try:
        result = query_all("SELECT role FROM users WHERE user_id = ?", (user_id,))
        if not result:
            raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
        if result[0][0] != "student":
            raise HTTPException(status_code=400, detail="学生アカウントではありません")

        execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        execute(
            "DELETE FROM direct_messages WHERE sender_id = ? OR recipient_id = ?",
            (user_id, user_id),
        )
        execute("DELETE FROM user_memories WHERE user_id = ?", (user_id,))
        execute("DELETE FROM google_accounts WHERE user_id = ?", (user_id,))
        execute("DELETE FROM users WHERE user_id = ?", (user_id,))

        return {"success": True, "message": "学生アカウントと関連データを削除しました"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/students/{user_id}", dependencies=[Depends(require_teacher)])
async def update_student(user_id: str, request: StudentUpdateRequest) -> Dict[str, Any]:
    try:
        result = query_all("SELECT role FROM users WHERE user_id = ?", (user_id,))
        if not result:
            raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
        if result[0][0] != "student":
            raise HTTPException(status_code=400, detail="学生アカウントではありません")

        updates = []
        params = []
        if request.name is not None:
            updates.append("name = ?")
            params.append(request.name)
        if request.grade is not None:
            updates.append("grade = ?")
            params.append(request.grade)
        if not updates:
            raise HTTPException(status_code=400, detail="更新する項目がありません")

        params.append(user_id)
        execute(f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?", tuple(params))

        return {"success": True, "message": "学生情報を更新しました"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
