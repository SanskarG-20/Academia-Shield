"""
Batch Management Router for Professors and Students (/api/v1/batches & /api/v1/student/batches).
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.dependencies import require_professor, require_student, require_any_user
from ..models.user import User
from ..models.batch import Batch, BatchMember, generate_batch_code
from ..models.audit_log import AuditLog
from ..schemas.batch import (
    BatchCreate,
    BatchUpdate,
    BatchJoinRequest,
    BatchProfessorResponse,
    BatchStudentResponse,
    BatchMemberResponse,
)

router = APIRouter(tags=["Batches"])

# Helper function to audit batch actions
def create_audit_entry(db: Session, user_id: str, action: str, resource_id: str, details: str):
    audit = AuditLog(
        actor_user_id=user_id,
        action=action,
        entity_type="BATCH",
        entity_id=resource_id,
        metadata_json={"details": details}
    )
    db.add(audit)
    db.commit()


# ==============================================================================
# PROFESSOR BATCH ENDPOINTS
# ==============================================================================

@router.post("/batches", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_batch(
    req: dict,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    Create a new batch (Professor / Admin only).
    Accepts both JSON schema format and raw dict payload from React form.
    """
    try:
        raw_name = req.get("name")
        if not raw_name or not str(raw_name).strip():
            raise HTTPException(status_code=400, detail="Batch name is required.")
        name = str(raw_name).strip()

        description = req.get("description")
        description = str(description).strip() if description else None

        code = req.get("code") or req.get("batch_code")
        if not code or not str(code).strip():
            code = generate_batch_code()
            while db.query(Batch).filter(Batch.batch_code == code).first():
                code = generate_batch_code()
        else:
            code = str(code).strip().upper()

        batch = Batch(
            professor_id=current_user.id,
            name=name,
            description=description,
            batch_code=code,
            is_active=True
        )
        db.add(batch)
        db.commit()
        db.refresh(batch)

        create_audit_entry(
            db=db,
            user_id=current_user.id,
            action="BATCH_CREATED",
            resource_id=batch.id,
            details=f"Created batch '{batch.name}' with code '{batch.batch_code}'"
        )

        return {
            "id": batch.id,
            "_id": batch.id,
            "professor_id": batch.professor_id,
            "professorId": batch.professor_id,
            "name": batch.name,
            "description": batch.description or "",
            "code": batch.batch_code,
            "batch_code": batch.batch_code,
            "is_active": batch.is_active,
            "member_count": 0,
            "students": [],
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "updated_at": batch.updated_at.isoformat() if batch.updated_at else None
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create batch: {str(e)}"
        )


@router.get("/batches", response_model=List[dict])
def get_batches_generic(
    current_user: User = Depends(require_any_user),
    db: Session = Depends(get_db)
):
    """
    List all batches for authenticated Professor or Student.
    """
    if current_user.role == "student":
        memberships = db.query(BatchMember).filter(
            BatchMember.student_id == current_user.id,
            BatchMember.status == "active"
        ).all()
        joined_batch_ids = [m.batch_id for m in memberships]
        batches = db.query(Batch).filter(Batch.id.in_(joined_batch_ids)).all() if joined_batch_ids else []
    else:
        batches = db.query(Batch).filter(Batch.professor_id == current_user.id).order_by(Batch.created_at.desc()).all()

    result = []
    for b in batches:
        memberships = db.query(BatchMember).filter(
            BatchMember.batch_id == b.id,
            BatchMember.status == "active"
        ).all()

        students_list = []
        for m in memberships:
            s = db.query(User).filter(User.id == m.student_id).first()
            if s:
                students_list.append({
                    "id": s.id,
                    "_id": s.id,
                    "name": s.full_name,
                    "student_name": s.full_name,
                    "sapId": s.institutional_id or "",
                    "sap_id": s.institutional_id or "",
                    "email": s.email
                })

        prof_user = db.query(User).filter(User.id == b.professor_id).first()
        prof_name = prof_user.full_name if prof_user else "Professor"

        result.append({
            "id": b.id,
            "_id": b.id,
            "professor_id": b.professor_id,
            "professorId": b.professor_id,
            "professor_name": prof_name,
            "professorName": prof_name,
            "name": b.name,
            "description": b.description or "",
            "code": b.batch_code,
            "batch_code": b.batch_code,
            "is_active": b.is_active,
            "member_count": len(students_list),
            "students": students_list,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "updated_at": b.updated_at.isoformat() if b.updated_at else None
        })
    return result


@router.get("/batches/{batch_id}", response_model=dict)
def get_batch_by_id_generic(
    batch_id: str,
    current_user: User = Depends(require_any_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed info for a batch (Professor or Student member).
    """
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch not found."
        )

    if current_user.role == "student":
        membership = db.query(BatchMember).filter(
            BatchMember.batch_id == batch_id,
            BatchMember.student_id == current_user.id,
            BatchMember.status == "active"
        ).first()
        if not membership and current_user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    memberships = db.query(BatchMember).filter(
        BatchMember.batch_id == batch.id,
        BatchMember.status == "active"
    ).all()

    students_list = []
    for m in memberships:
        s = db.query(User).filter(User.id == m.student_id).first()
        if s:
            students_list.append({
                "id": s.id,
                "_id": s.id,
                "name": s.full_name,
                "student_name": s.full_name,
                "sapId": s.institutional_id or "",
                "sap_id": s.institutional_id or "",
                "email": s.email
            })

    return {
        "id": batch.id,
        "_id": batch.id,
        "professor_id": batch.professor_id,
        "professorId": batch.professor_id,
        "name": batch.name,
        "description": batch.description or "",
        "code": batch.batch_code,
        "batch_code": batch.batch_code,
        "is_active": batch.is_active,
        "member_count": len(students_list),
        "students": students_list,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "updated_at": batch.updated_at.isoformat() if batch.updated_at else None
    }


@router.patch("/batches/{batch_id}", response_model=BatchProfessorResponse)
def update_batch(
    batch_id: str,
    req: BatchUpdate,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    Update batch name, description, or active status (Owner only).
    """
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found.")
    if current_user.role != "admin" and batch.professor_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")

    if req.name is not None:
        batch.name = req.name.strip()
    if req.description is not None:
        batch.description = req.description.strip()
    if req.is_active is not None:
        batch.is_active = req.is_active

    db.commit()
    db.refresh(batch)

    member_count = db.query(BatchMember).filter(
        BatchMember.batch_id == batch.id,
        BatchMember.status == "active"
    ).count()

    return BatchProfessorResponse(
        id=batch.id,
        professor_id=batch.professor_id,
        name=batch.name,
        description=batch.description,
        batch_code=batch.batch_code,
        is_active=batch.is_active,
        member_count=member_count,
        created_at=batch.created_at,
        updated_at=batch.updated_at
    )


@router.post("/batches/{batch_id}/regenerate-code", response_model=BatchProfessorResponse)
def regenerate_batch_code(
    batch_id: str,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    Regenerate a new random 6-character batch code for student joins.
    """
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found.")
    if current_user.role != "admin" and batch.professor_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")

    new_code = generate_batch_code()
    while db.query(Batch).filter(Batch.batch_code == new_code).first():
        new_code = generate_batch_code()

    old_code = batch.batch_code
    batch.batch_code = new_code
    db.commit()
    db.refresh(batch)

    create_audit_entry(
        db=db,
        user_id=current_user.id,
        action="BATCH_CODE_REGENERATED",
        resource_id=batch.id,
        details=f"Regenerated batch code for '{batch.name}' from '{old_code}' to '{new_code}'"
    )

    member_count = db.query(BatchMember).filter(
        BatchMember.batch_id == batch.id,
        BatchMember.status == "active"
    ).count()

    return BatchProfessorResponse(
        id=batch.id,
        professor_id=batch.professor_id,
        name=batch.name,
        description=batch.description,
        batch_code=batch.batch_code,
        is_active=batch.is_active,
        member_count=member_count,
        created_at=batch.created_at,
        updated_at=batch.updated_at
    )


@router.get("/batches/{batch_id}/members", response_model=List[BatchMemberResponse])
def get_batch_members(
    batch_id: str,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    List enrolled members of a batch (Professor / Admin only).
    """
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found.")
    if current_user.role != "admin" and batch.professor_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")

    memberships = db.query(BatchMember).filter(
        BatchMember.batch_id == batch_id,
        BatchMember.status == "active"
    ).all()

    result = []
    for m in memberships:
        student = db.query(User).filter(User.id == m.student_id).first()
        if student:
            result.append(BatchMemberResponse(
                id=m.id,
                student_id=student.id,
                student_name=student.full_name,
                student_email=student.email,
                status=m.status,
                joined_at=m.joined_at
            ))
    return result


@router.delete("/batches/{batch_id}/members/{student_id}")
def remove_batch_member(
    batch_id: str,
    student_id: str,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    Remove a student from a batch (Professor / Admin only).
    """
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found.")
    if current_user.role != "admin" and batch.professor_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")

    membership = db.query(BatchMember).filter(
        BatchMember.batch_id == batch_id,
        BatchMember.student_id == student_id,
        BatchMember.status == "active"
    ).first()
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found in this batch.")

    membership.status = "removed"
    db.commit()

    create_audit_entry(
        db=db,
        user_id=current_user.id,
        action="BATCH_MEMBER_REMOVED",
        resource_id=batch.id,
        details=f"Removed student '{student_id}' from batch '{batch.name}'"
    )
    return {"status": "ok", "message": "Member removed from batch."}



# ==============================================================================
# STUDENT BATCH ENDPOINTS
# ==============================================================================

@router.post("/student/batches/join", response_model=BatchStudentResponse, status_code=status.HTTP_200_OK)
@router.post("/batches/join", response_model=BatchStudentResponse, status_code=status.HTTP_200_OK)
def join_batch(
    req: dict,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """
    Join a batch using its unique batch_code (Student only).
    """
    raw_code = req.get("batch_code") or req.get("code") or ""
    clean_code = str(raw_code).strip().upper()
    batch = db.query(Batch).filter(Batch.batch_code == clean_code).first()


    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid batch code. Please check and try again."
        )

    if not batch.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This batch is currently inactive."
        )

    # Check if student is already an active member
    existing = db.query(BatchMember).filter(
        BatchMember.batch_id == batch.id,
        BatchMember.student_id == current_user.id
    ).first()

    if existing:
        if existing.status == "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are already a member of this batch."
            )
        else:
            # Re-activate membership
            existing.status = "active"
            db.commit()
            db.refresh(existing)
            member = existing
    else:
        member = BatchMember(
            batch_id=batch.id,
            student_id=current_user.id,
            status="active"
        )
        db.add(member)
        db.commit()
        db.refresh(member)

    create_audit_entry(
        db=db,
        user_id=current_user.id,
        action="BATCH_JOINED",
        resource_id=batch.id,
        details=f"Student '{current_user.full_name}' joined batch '{batch.name}'"
    )

    return BatchStudentResponse(
        id=batch.id,
        name=batch.name,
        description=batch.description,
        is_active=batch.is_active,
        joined_at=member.joined_at,
        created_at=batch.created_at,
        updated_at=batch.updated_at
    )


@router.get("/student/batches", response_model=List[BatchStudentResponse])
def get_student_batches(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """
    List only batches actively joined by the authenticated student.
    NEVER includes batch_code or member lists.
    """
    memberships = db.query(BatchMember).filter(
        BatchMember.student_id == current_user.id,
        BatchMember.status == "active"
    ).all()

    result = []
    for m in memberships:
        b = db.query(Batch).filter(Batch.id == m.batch_id).first()
        if b:
            result.append(BatchStudentResponse(
                id=b.id,
                name=b.name,
                description=b.description,
                is_active=b.is_active,
                joined_at=m.joined_at,
                created_at=b.created_at,
                updated_at=b.updated_at
            ))
    return result


@router.get("/student/batches/{batch_id}", response_model=BatchStudentResponse)
def get_student_batch_by_id(
    batch_id: str,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """
    Get details of a joined batch for student.
    STRICT RULE: Returns 403 Forbidden if the student is not an active member.
    """
    membership = db.query(BatchMember).filter(
        BatchMember.batch_id == batch_id,
        BatchMember.student_id == current_user.id,
        BatchMember.status == "active"
    ).first()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You have not joined this batch."
        )

    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch not found."
        )

    return BatchStudentResponse(
        id=batch.id,
        name=batch.name,
        description=batch.description,
        is_active=batch.is_active,
        joined_at=membership.joined_at,
        created_at=batch.created_at,
        updated_at=batch.updated_at
    )
