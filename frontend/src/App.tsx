import React, { useEffect, useState } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Layout } from './components/layout/Layout';
import { Auth } from './pages/Auth';
import { AccessDenied } from './components/AccessDenied';

import { Dashboard } from './pages/Dashboard';
import { Sessions } from './pages/Sessions';
import { Rules } from './pages/Rules';
import { Logs } from './pages/Logs';
import { LiveLogs } from './pages/LiveLogs';
import { Settings } from './pages/Settings';
import { StudentProfile } from './pages/StudentProfile';
import { ProfessorProfile } from './pages/ProfessorProfile';
import { Batches } from './pages/Batches';
import { BatchDetails } from './pages/BatchDetails';
import { StudentSession } from './pages/StudentSession';
import { JoinBatch } from './pages/JoinBatch';
import { Admin } from './pages/Admin';
import { StudentEngagement } from './pages/StudentEngagement';
import { AUTH_STATE_CHANGED_EVENT } from './lib/api';

// Protected Route Guard
const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const location = useLocation();
  const [isAuthenticated, setIsAuthenticated] = useState(
    () => localStorage.getItem('isAuthenticated') === 'true'
  );

  useEffect(() => {
    const syncAuthState = () => setIsAuthenticated(localStorage.getItem('isAuthenticated') === 'true');
    window.addEventListener(AUTH_STATE_CHANGED_EVENT, syncAuthState);
    return () => window.removeEventListener(AUTH_STATE_CHANGED_EVENT, syncAuthState);
  }, []);

  if (!isAuthenticated) {
    return <Navigate to="/auth" state={{ from: location }} replace />;
  }
  return <>{children}</>;
};

// Professor RBAC Guard
const ProfessorOnlyRoute = ({ children }: { children: React.ReactNode }) => {
  const [role, setRole] = useState(() => localStorage.getItem('userRole'));

  useEffect(() => {
    const syncAuthState = () => setRole(localStorage.getItem('userRole'));
    window.addEventListener(AUTH_STATE_CHANGED_EVENT, syncAuthState);
    return () => window.removeEventListener(AUTH_STATE_CHANGED_EVENT, syncAuthState);
  }, []);

  if (role === 'student') {
    return <AccessDenied requiredRole="professor" />;
  }
  return <>{children}</>;
};

// Student RBAC Guard
const StudentOnlyRoute = ({ children }: { children: React.ReactNode }) => {
  const [role, setRole] = useState(() => localStorage.getItem('userRole'));

  useEffect(() => {
    const syncAuthState = () => setRole(localStorage.getItem('userRole'));
    window.addEventListener(AUTH_STATE_CHANGED_EVENT, syncAuthState);
    return () => window.removeEventListener(AUTH_STATE_CHANGED_EVENT, syncAuthState);
  }, []);

  if (role === 'professor') {
    return <AccessDenied requiredRole="student" />;
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
      {/* Public Authentication Routes */}
      <Route path="/auth" element={<Auth />} />
      <Route path="/login" element={<Auth />} />
      <Route path="/select-user" element={<Auth />} />
      <Route path="/login/student" element={<Auth />} />
      <Route path="/login/professor" element={<Auth />} />

      {/* Protected Standalone Profiles & Join */}
      <Route
        path="/student/profile"
        element={
          <ProtectedRoute>
            <StudentOnlyRoute>
              <StudentProfile />
            </StudentOnlyRoute>
          </ProtectedRoute>
        }
      />
      <Route
        path="/student/join-batch"
        element={
          <ProtectedRoute>
            <StudentOnlyRoute>
              <JoinBatch />
            </StudentOnlyRoute>
          </ProtectedRoute>
        }
      />
      <Route
        path="/professor/profile"
        element={
          <ProtectedRoute>
            <ProfessorOnlyRoute>
              <ProfessorProfile />
            </ProfessorOnlyRoute>
          </ProtectedRoute>
        }
      />

      {/* Root path smart redirect */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <RoleBasedRedirect />
          </ProtectedRoute>
        }
      />

      {/* Main App Layout */}
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        {/* Professor Live Command Center */}
        <Route
          path="dashboard"
          element={
            <ProfessorOnlyRoute>
              <Dashboard />
            </ProfessorOnlyRoute>
          }
        />

        {/* Student Session & Portal */}
        <Route
          path="student/session"
          element={
            <StudentOnlyRoute>
              <StudentSession />
            </StudentOnlyRoute>
          }
        />
        <Route
          path="student/sessions"
          element={
            <StudentOnlyRoute>
              <StudentSession />
            </StudentOnlyRoute>
          }
        />
        <Route
          path="student/batches"
          element={
            <StudentOnlyRoute>
              <Batches />
            </StudentOnlyRoute>
          }
        />

        {/* Professor Sessions Management */}
        <Route
          path="sessions"
          element={
            <ProfessorOnlyRoute>
              <Sessions />
            </ProfessorOnlyRoute>
          }
        />

        {/* Professor Student Engagement Intelligence */}
        <Route
          path="professor/student-engagement"
          element={
            <ProfessorOnlyRoute>
              <StudentEngagement />
            </ProfessorOnlyRoute>
          }
        />

        {/* Professor Batch Management */}
        <Route
          path="batches"
          element={
            <ProfessorOnlyRoute>
              <Batches />
            </ProfessorOnlyRoute>
          }
        />
        <Route
          path="batches/:id"
          element={
            <ProfessorOnlyRoute>
              <BatchDetails />
            </ProfessorOnlyRoute>
          }
        />

        {/* Professor Rules & Logs */}
        <Route
          path="rules"
          element={
            <ProfessorOnlyRoute>
              <Rules />
            </ProfessorOnlyRoute>
          }
        />
        <Route
          path="logs"
          element={
            <ProfessorOnlyRoute>
              <Logs />
            </ProfessorOnlyRoute>
          }
        />
        <Route
          path="logs/live"
          element={
            <ProfessorOnlyRoute>
              <LiveLogs />
            </ProfessorOnlyRoute>
          }
        />
        <Route
          path="admin"
          element={
            <ProfessorOnlyRoute>
              <Admin />
            </ProfessorOnlyRoute>
          }
        />

        {/* Shared Settings */}
        <Route path="settings" element={<Settings />} />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/auth" replace />} />
    </Routes>
  );
};

const RoleBasedRedirect: React.FC = () => {
  const role = localStorage.getItem('userRole');
  if (role === 'student') {
    return <Navigate to="/student/session" replace />;
  }
  return <Navigate to="/dashboard" replace />;
};
