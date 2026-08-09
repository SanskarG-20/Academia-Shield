import React, { useEffect } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Layout } from './components/layout/Layout';
import { Dashboard } from './pages/Dashboard';
import { Sessions } from './pages/Sessions';
import { Rules } from './pages/Rules';
import { Logs } from './pages/Logs';
import { LiveLogs } from './pages/LiveLogs';
import { Settings } from './pages/Settings';
import { SelectUser } from './pages/SelectUser';
import { LoginStudent } from './pages/LoginStudent';
import { LoginStudentOTP } from './pages/LoginStudentOTP';
import { LoginProfessor } from './pages/LoginProfessor';
import { StudentProfile } from './pages/StudentProfile';
import { ProfessorProfile } from './pages/ProfessorProfile';
import { Batches } from './pages/Batches';
import { BatchDetails } from './pages/BatchDetails';
import { StudentSession } from './pages/StudentSession';
import { JoinBatch } from './pages/JoinBatch';

// Protected Route Wrapper
const ProtectedRoute = ({ children }: { children?: React.ReactNode }) => {
  const isAuthenticated = localStorage.getItem('isAuthenticated') === 'true';
  if (!isAuthenticated) {
    return <Navigate to="/select-user" replace />;
  }
  return <>{children}</>;
};

// Admin Route Wrapper
const AdminRoute = ({ children }: { children?: React.ReactNode }) => {
  const userRole = localStorage.getItem('userRole');
  if (userRole === 'student') {
    // Redirect students to dashboard if they try to access admin routes
    return <Navigate to="/dashboard" replace />;
  }
  return <>{children}</>;
};

export const App: React.FC = () => {
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return (
    <Routes>
      {/* Public Auth Routes */}
      <Route path="/" element={<Navigate to="/select-user" replace />} />
      <Route path="/select-user" element={<SelectUser />} />
      <Route path="/login/student" element={<LoginStudent />} />
      <Route path="/login/student/otp" element={<LoginStudentOTP />} />
      <Route path="/login/professor" element={<LoginProfessor />} />

      {/* Onboarding Routes - Protected but standalone (no sidebar) */}
      <Route path="/student/profile" element={<ProtectedRoute><StudentProfile /></ProtectedRoute>} />
      <Route path="/student/join-batch" element={<ProtectedRoute><JoinBatch /></ProtectedRoute>} />
      <Route path="/professor/profile" element={<ProtectedRoute><ProfessorProfile /></ProtectedRoute>} />

      {/* Main App Routes */}
      <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        {/* Dashboard is accessible to all roles (component handles role-specific content) */}
        <Route path="dashboard" element={<Dashboard />} />
        
        {/* Dedicated Student Session View */}
        <Route path="student/session" element={<StudentSession />} />
        
        <Route path="sessions" element={<Sessions />} />
        
        {/* Batch Management - Professors Only */}
        <Route path="batches" element={<AdminRoute><Batches /></AdminRoute>} />
        <Route path="batches/:id" element={<AdminRoute><BatchDetails /></AdminRoute>} />
        
        <Route path="rules" element={<AdminRoute><Rules /></AdminRoute>} />
        <Route path="logs" element={<AdminRoute><Logs /></AdminRoute>} />
        <Route path="monitor" element={<AdminRoute><LiveLogs /></AdminRoute>} />
        <Route path="settings" element={<Settings />} />
      </Route>
      
      {/* Fallback */}
      <Route path="*" element={<Navigate to="/select-user" replace />} />
    </Routes>
  );
};