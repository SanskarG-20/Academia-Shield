import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { User, BadgeCheck, Briefcase, Mail, CheckCircle } from 'lucide-react';
import { Input, Select } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { getMe, updateMe } from '../lib/api';

export const ProfessorProfile: React.FC = () => {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    fullName: '',
    department: '',
    employeeId: '',
    designation: '',
    email: ''
  });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadProfile = async () => {
      try {
        const profile = await getMe();
        setFormData({
          fullName: profile.name === 'New Faculty' ? '' : (profile.name || ''),
          department: profile.department === 'Pending' ? '' : (profile.department || ''),
          employeeId: '',
          designation: profile.designation === 'Pending' ? '' : (profile.designation || ''),
          email: profile.email || '',
        });
      } catch (err: any) {
        setError(err.message || 'Failed to load profile data.');
      }
    };

    loadProfile();
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!formData.fullName || !formData.department || !formData.designation) {
      setError('All fields are mandatory for faculty registration.');
      return;
    }

    setIsLoading(true);

    try {
      await updateMe({
        name: formData.fullName,
        department: formData.department,
        designation: formData.designation,
      });
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.message || 'Failed to update profile.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-gradient-to-br from-blue-50 to-slate-100 dark:from-slate-900 dark:to-slate-800 p-4 font-sans">
      <div className="max-w-2xl w-full bg-white dark:bg-slate-800 rounded-2xl shadow-xl overflow-hidden border border-slate-200 dark:border-slate-700 animate-fade-in">
        
        {/* Header */}
        <div className="bg-white dark:bg-slate-800 border-b border-slate-100 dark:border-slate-700 p-6 sm:p-8 text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 mb-4">
            <BadgeCheck size={32} />
          </div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Faculty Profile Setup</h1>
          <p className="text-slate-500 dark:text-slate-400 mt-2">
            Complete your administrative profile to access the dashboard.
          </p>
        </div>

        {/* Form */}
        <div className="p-6 sm:p-8">
          {error && (
            <div className="mb-6 p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-lg border border-red-200 dark:border-red-800 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Email - Read Only */}
              <div className="col-span-1 md:col-span-2">
                <Input
                  label="Institutional Email"
                  name="email"
                  value={formData.email}
                  disabled
                  icon={<Mail size={16} />}
                  className="bg-slate-50 dark:bg-slate-900 text-slate-500 cursor-not-allowed"
                />
              </div>

              {/* Full Name */}
              <Input
                label="Full Name"
                name="fullName"
                placeholder="Dr. Name Surname"
                value={formData.fullName}
                onChange={handleChange}
                icon={<User size={16} />}
              />

              {/* Employee ID */}
              <Input
                label="Employee / Staff ID"
                name="employeeId"
                placeholder="e.g. EMP-2023-001"
                value={formData.employeeId}
                onChange={handleChange}
                icon={<Briefcase size={16} />}
              />

              {/* Department */}
              <Select
                label="Department"
                name="department"
                value={formData.department}
                onChange={handleChange}
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

              {/* Designation */}
              <Select
                label="Designation"
                name="designation"
                value={formData.designation}
                onChange={handleChange}
                options={[
                  { value: '', label: 'Select Designation' },
                  { value: 'AP', label: 'Assistant Professor' },
                  { value: 'ASP', label: 'Associate Professor' },
                  { value: 'PROF', label: 'Professor' },
                  { value: 'HOD', label: 'Head of Department' },
                  { value: 'ADMIN', label: 'Administrator' },
                  { value: 'LAB', label: 'Lab Instructor' },
                ]}
              />
            </div>

            <div className="pt-6">
              <Button 
                type="submit" 
                className="w-full bg-blue-600 hover:bg-blue-700 text-white" 
                size="lg"
                disabled={isLoading}
                icon={isLoading ? null : <CheckCircle size={18} />}
              >
                {isLoading ? 'Finalizing Setup...' : 'Complete Registration'}
              </Button>
            </div>

          </form>
        </div>
      </div>
    </div>
  );
};