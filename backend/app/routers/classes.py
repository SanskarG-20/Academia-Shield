"""
Classes Router (/api/v1/classes).
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.dependencies import get_current_user, require_professor
from ..models.user import User
from ..models.class_model import ClassModel, ClassMember
from ..schemas.class_schema import ClassCreate, ClassResponse, AddStudentRequest
from ..services.class_service import ClassService

router = APIRouter(prefix="/classes", tags=["Classes"])

@router.post("", response_model=ClassResponse, status_code=status.HTTP_201_CREATED)
def create_class(
    req: ClassCreate,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Create a new course class (Professor/Admin only)."""
    return ClassService.create_class(req, professor, db)

@router.get("", response_model=List[ClassResponse])
def list_classes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List classes accessible to the authenticated user."""
    classes = ClassService.get_classes_for_user(current_user, db)
    results = []
    for c in classes:
        resp = ClassResponse.model_validate(c)
        resp.student_count = db.query(ClassMember).filter(ClassMember.class_id == c.id).count()
        results.append(resp)
    return results

@router.get("/{class_id}", response_model=ClassResponse)
def get_class_by_id(
    class_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetch specific class details."""
    c = db.query(ClassModel).filter(ClassModel.id == class_id).first()
    if not c:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    
    # Ownership/Membership check
    if current_user.role == "student":
        is_member = db.query(ClassMember).filter(ClassMember.class_id == class_id, ClassMember.student_id == current_user.id).first()
        if not is_member:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not enrolled in this class")
    elif current_user.role == "professor" and c.professor_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this class")

    resp = ClassResponse.model_validate(c)
    resp.student_count = db.query(ClassMember).filter(ClassMember.class_id == c.id).count()
    return resp

@router.post("/{class_id}/students")
def add_student_to_class(
    class_id: str,
    req: AddStudentRequest,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Enroll a student into a class (Professor/Admin only)."""
    member = ClassService.add_student_to_class(class_id, req.student_email_or_id, professor, db)
    return {"status": "enrolled", "class_id": class_id, "student_id": member.student_id}

@router.delete("/{class_id}/students/{student_id}")
def remove_student_from_class(
    class_id: str,
    student_id: str,
    professor: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Remove a student from a class (Professor/Admin only)."""
    class_obj = db.query(ClassModel).filter(ClassModel.id == class_id).first()
    if not class_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    if professor.role != "admin" and class_obj.professor_id != professor.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only class owner can manage students")

    db.query(ClassMember).filter(ClassMember.class_id == class_id, ClassMember.student_id == student_id).delete()
    db.commit()
    return {"status": "removed", "class_id": class_id, "student_id": student_id}
