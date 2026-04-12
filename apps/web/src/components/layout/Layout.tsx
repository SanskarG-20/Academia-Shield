import React from 'react';
import { Sidebar } from './Sidebar';
import { Navbar } from './Navbar';
import { Outlet } from 'react-router-dom';

export const Layout: React.FC = () => {
  return (
    <div className="flex min-h-screen bg-slate-50 dark:bg-dark-bg text-slate-900 dark:text-dark-text font-sans">
      <Sidebar />
      <div className="flex flex-1 flex-col pl-64 transition-all">
        <Navbar />
        <main className="flex-1 p-6 lg:p-8 overflow-x-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
