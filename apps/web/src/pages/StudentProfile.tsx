import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { User, BookOpen, Hash, CheckCircle } from 'lucide-react';
import { Input, Select } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { createStudentProfile } from '../lib/api';

export const StudentProfile: React.FC = () => {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    fullName: '',
    department: '',
    rollNumber: '',
    yearOfStudy: '',
    sapId: ''
  });
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Load verified credentials from login session
    const storedSapId = localStorage.getItem('tempSapId');
    if (storedSapId) {
        setFormData(prev => ({ ...prev, sapId: storedSapId }));
    } else {
      navigate('/login/student');
    }
    }, [navigate]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!formData.fullName || !formData.department || !formData.rollNumber || !formData.yearOfStudy || !formData.sapId) {
      setError('Please fill in all required fields.');
      return;
    }

    setIsLoading(true);

    try {
      await createStudentProfile({
        sapId: formData.sapId,
        name: formData.fullName,
        department: formData.department,
        rollNumber: formData.rollNumber,
        year: formData.yearOfStudy,
      });

      navigate('/student/join-batch');
    } catch (err: any) {
      setError(err.message || 'Failed to save profile.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-gradient-to-br from-blue-50 to-slate-100 dark:from-slate-900 dark:to-slate-800 p-4 font-sans">
      <div className="max-w-2xl w-full bg-white dark:bg-slate-800 rounded-2xl shadow-xl overflow-hidden border border-slate-200 dark:border-slate-700 animate-fade-in">
        
        {/* Header */}
        <div className="bg-white dark:bg-slate-800 border-b border-slate-100 dark:border-slate-700 p-6 sm:p-8 text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-brand-50 dark:bg-brand-900/20 text-brand-600 dark:text-brand-400 mb-4">
            <User size={32} />
          </div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Complete Your Profile</h1>
          <p className="text-slate-500 dark:text-slate-400 mt-2">
            Please provide your academic details to finalize your account setup.
          </p>
        </div>

        {/* Form */}
        <div className="p-6 sm:p-8">
          {error && (
            <div className="mb-6 p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-lg border border-red-200 dark:border-red-800">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Verified Credentials Section */}
              <div className="col-span-1 md:col-span-2 p-4 bg-slate-50 dark:bg-slate-900/50 rounded-xl border border-slate-100 dark:border-slate-700">
                <Input
                  label="SAP ID"
                  name="sapId"
                  value={formData.sapId}
                  disabled
                  icon={<Hash size={16} />}
                  className="bg-white dark:bg-slate-800 text-slate-500 cursor-not-allowed border-slate-200 dark:border-slate-700"
                />
              </div>

              {/* Full Name */}
              <Input
                label="Full Name"
                name="fullName"
                placeholder="e.g. John Doe"
                value={formData.fullName}
                onChange={handleChange}
                icon={<User size={16} />}
              />
              
              {/* Roll Number */}
              <Input
                label="Roll Number"
                name="rollNumber"
                placeholder="e.g. 21CSE045"
                value={formData.rollNumber}
                onChange={handleChange}
                icon={<BookOpen size={16} />}
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

              {/* Year of Study */}
              <Select
                label="Year of Study"
                name="yearOfStudy"
                value={formData.yearOfStudy}
                onChange={handleChange}
                options={[
                  { value: '', label: 'Select Year' },
                  { value: '1', label: '1st Year' },
                  { value: '2', label: '2nd Year' },
                  { value: '3', label: '3rd Year' },
                  { value: '4', label: '4th Year' },
                ]}
              />
            </div>

            <div className="pt-6">
              <Button 
                type="submit" 
                className="w-full" 
                size="lg"
                disabled={isLoading}
                icon={isLoading ? null : <CheckCircle size={18} />}
              >
                {isLoading ? 'Save & Continue' : 'Save & Continue'}
              </Button>
            </div>

          </form>
        </div>
      </div>
    </div>
  );
};
