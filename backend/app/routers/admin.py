from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from app.db import teacher
<<<<<<< HEAD

router = APIRouter(prefix="/api/admin", tags=["admin"])

=======
from app.db.sqlite import query_all, execute, now_iso
import sqlite3

router = APIRouter(prefix="/api/admin", tags=["admin"])

DB_PATH = "student_support.db"

>>>>>>> 4c980dc8656a8e8f7b9f31e5a8b1edfe50c878ee

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
<<<<<<< HEAD
=======
        raise HTTPException(status_code=500, detail=str(e))


# ========== 学生管理用エンドポイント ==========

@router.get("/students")
async def get_students() -> Dict[str, Any]:
    """全学生ユーザーを取得"""
    try:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        
        cur.execute("""
            SELECT u.user_id, u.name, u.grade, g.email, u.created_at
            FROM users u
            LEFT JOIN google_accounts g ON u.user_id = g.user_id
            WHERE u.role = 'student'
            ORDER BY u.grade, u.name
        """)
        
        rows = cur.fetchall()
        con.close()
        
        students = [dict(row) for row in rows]
        
        # 学年別に分類
        students_by_grade = {}
        for student in students:
            grade = student.get("grade") or "未設定"
            if grade not in students_by_grade:
                students_by_grade[grade] = []
            students_by_grade[grade].append(student)
        
        return {
            "success": True,
            "students": students,
            "students_by_grade": students_by_grade
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/students/{user_id}")
async def delete_student(user_id: str) -> Dict[str, Any]:
    """学生の削除（関連データも削除）"""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        
        # 学生かどうか確認
        cur.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
        result = cur.fetchone()
        
        if not result:
            con.close()
            raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
        
        if result[0] != 'student':
            con.close()
            raise HTTPException(status_code=400, detail="学生アカウントではありません")
        
        # 関連データを削除
        cur.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        cur.execute("DELETE FROM direct_messages WHERE sender_id = ? OR recipient_id = ?", (user_id, user_id))
        cur.execute("DELETE FROM user_memories WHERE user_id = ?", (user_id,))
        cur.execute("DELETE FROM google_accounts WHERE user_id = ?", (user_id,))
        cur.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        
        con.commit()
        deleted = cur.rowcount > 0
        con.close()
        
        return {
            "success": True,
            "message": "学生アカウントと関連データを削除しました"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class StudentUpdateRequest(BaseModel):
    name: str = None
    grade: str = None


@router.put("/students/{user_id}")
async def update_student(user_id: str, request: StudentUpdateRequest) -> Dict[str, Any]:
    """学生情報の更新"""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        
        # 学生かどうか確認
        cur.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
        result = cur.fetchone()
        
        if not result:
            con.close()
            raise HTTPException(status_code=404, detail="ユーザーが見つかりません")
        
        if result[0] != 'student':
            con.close()
            raise HTTPException(status_code=400, detail="学生アカウントではありません")
        
        # 更新処理
        updates = []
        params = []
        
        if request.name is not None:
            updates.append("name = ?")
            params.append(request.name)
        
        if request.grade is not None:
            updates.append("grade = ?")
            params.append(request.grade)
        
        if not updates:
            con.close()
            raise HTTPException(status_code=400, detail="更新する項目がありません")
        
        params.append(user_id)
        query = f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?"
        
        cur.execute(query, tuple(params))
        con.commit()
        con.close()
        
        return {
            "success": True,
            "message": "学生情報を更新しました"
        }
    except HTTPException:
        raise
    except Exception as e:
>>>>>>> 4c980dc8656a8e8f7b9f31e5a8b1edfe50c878ee
        raise HTTPException(status_code=500, detail=str(e))