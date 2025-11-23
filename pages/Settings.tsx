import React, { useState, useEffect } from 'react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input, Select } from '../components/ui/Input';
import { User, Moon, Sun, Lock, Info } from 'lucide-react';

export const Settings: React.FC = () => {
  const [darkMode, setDarkMode] = useState(false);
  const [userProfile, setUserProfile] = useState({
    name: '',
    email: '',
    department: '',
    role: ''
  });

  useEffect(() => {
    if (document.documentElement.classList.contains('dark')) {
      setDarkMode(true);
    }

    const role = localStorage.getItem('userRole') || '';
    const name = localStorage.getItem('userName') || '';
    const email = localStorage.getItem('userEmail') || '';
    
    let department = '';
    
    // Attempt to load department from stored profiles
    if (role === 'student') {
        const stored = localStorage.getItem('studentProfile');
        if (stored) {
            try {
                const data = JSON.parse(stored);
                department = data.department || '';
            } catch (e) { console.error('Error parsing student profile', e); }
        }
    } else {
        const stored = localStorage.getItem('professorProfile');
        if (stored) {
            try {
                const data = JSON.parse(stored);
                department = data.department || '';
            } catch (e) { console.error('Error parsing professor profile', e); }
        }
    }

    setUserProfile({ name, email, department, role });
  }, []);

  const toggleDarkMode = () => {
    const isDark = !darkMode;
    setDarkMode(isDark);
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  };

  const handleSave = () => {
    // Update local storage
    localStorage.setItem('userName', userProfile.name);
    
    if (userProfile.role === 'student') {
        const stored = JSON.parse(localStorage.getItem('studentProfile') || '{}');
        const updated = { ...stored, fullName: userProfile.name, department: userProfile.department };
        localStorage.setItem('studentProfile', JSON.stringify(updated));
    } else {
        const stored = JSON.parse(localStorage.getItem('professorProfile') || '{}');
        const updated = { ...stored, fullName: userProfile.name, department: userProfile.department };
        localStorage.setItem('professorProfile', JSON.stringify(updated));
    }
    
    alert('Profile changes saved successfully.');
    // Force reload to update Navbar/Sidebar if name changed
    window.location.reload();
  };

  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Settings</h1>

      <Card title="Profile Information">
        <div className="flex items-start gap-6">
          <div className="h-20 w-20 rounded-full bg-slate-200 dark:bg-slate-700 flex items-center justify-center text-slate-400 shrink-0">
            <User size={40} />
          </div>
          <div className="flex-1 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Input 
                label="Full Name" 
                value={userProfile.name} 
                onChange={(e) => setUserProfile({...userProfile, name: e.target.value})}
              />
              <Input 
                label="Email" 
                value={userProfile.email} 
                disabled 
                className="bg-slate-50 dark:bg-slate-900 text-slate-500 cursor-not-allowed"
              />
            </div>
            
            <Select 
                label="Department"
                value={userProfile.department}
                onChange={(e) => setUserProfile({...userProfile, department: e.target.value})}
                options={[
                  { value: '', label: 'Select Department' },
                  { value: 'CE', label: 'Computer Engineering' },
                  { value: 'IT', label: 'Information Technology' },
                  { value: 'AIDS', label: 'AI & Data Science' },
                  { value: 'AIML', label: 'AI & Machine Learning' },
                  { value: 'CSE_ICB', label: 'CSE (ICB)' },
                  { value: 'CSE_DS', label: 'CSE (DS)' },
                  { value: 'MECH', label: 'Mechanical Engineering' },
                  { value: 'EXTC', label: 'EXTC' },
                ]}
            />
            
            <div className="flex justify-end">
              <Button onClick={handleSave}>Save Changes</Button>
            </div>
          </div>
        </div>
      </Card>

      <Card title="Appearance">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="font-medium text-slate-900 dark:text-white">Theme Preference</h4>
            <p className="text-sm text-slate-500">Toggle between light and dark modes for the dashboard.</p>
          </div>
          <Button 
            variant="secondary" 
            icon={darkMode ? <Sun size={18} /> : <Moon size={18} />}
            onClick={toggleDarkMode}
          >
            {darkMode ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
          </Button>
        </div>
      </Card>

      <Card title="Security">
        <div className="space-y-4">
          <div className="flex items-center justify-between pb-4 border-b border-slate-100 dark:border-slate-700">
            <div>
              <h4 className="font-medium text-slate-900 dark:text-white">Password</h4>
              <p className="text-sm text-slate-500">Last changed 30 days ago.</p>
            </div>
            <Button variant="secondary" icon={<Lock size={16} />}>Change Password</Button>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <h4 className="font-medium text-slate-900 dark:text-white">Two-Factor Authentication</h4>
              <p className="text-sm text-slate-500">Secure your account with 2FA.</p>
            </div>
            <div className="flex items-center">
               <span className="mr-3 text-sm text-emerald-600 font-medium">Enabled</span>
               <Button variant="secondary" size="sm">Configure</Button>
            </div>
          </div>
        </div>
      </Card>

      <Card>
        <div className="flex gap-4 items-center text-slate-500 text-sm">
          <Info size={20} />
          <div>
            <p className="font-medium text-slate-900 dark:text-white">Academia Shield v2.4.1</p>
            <p>Build 2023.10.25. Enterprise License.</p>
          </div>
        </div>
      </Card>
    </div>
  );
};