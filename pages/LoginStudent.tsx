import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { GraduationCap, AlertCircle, Phone, Send, Hash } from 'lucide-react';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';

export const LoginStudent: React.FC = () => {
  const navigate = useNavigate();
  const [phoneNumber, setPhoneNumber] = useState('');
  const [sapId, setSapId] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handlePhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    // Only allow numbers
    if (/^\d*$/.test(value) && value.length <= 10) {
      setPhoneNumber(value);
      setError(null);
    }
  };

  const handleRequestOtp = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // SAP ID Validation (11 digits)
    if (!sapId.trim() || sapId.length !== 11 || !/^\d+$/.test(sapId)) {
      setError('Invalid SAP ID. Please enter exactly 11 digits.');
      return;
    }

    // Phone Number Validation
    if (phoneNumber.length !== 10) {
      setError('Invalid Mobile Number. Please enter a 10-digit number.');
      return;
    }

    setIsLoading(true);
    
    // Simulate API call to send OTP
    // Mock API POST /auth/student/request-otp
    setTimeout(() => {
      localStorage.setItem('tempPhoneNumber', phoneNumber);
      localStorage.setItem('tempSapId', sapId);
      setIsLoading(false);
      
      // MOCK SMS SIMULATION
      alert(`[MOCK SMS] \n\nSent to: +91 ${phoneNumber}\nSAP ID: ${sapId}\nYour Academia Shield Verification Code is: 123456`);
      
      // Redirect to OTP verification
      navigate('/login/student/otp');
    }, 1500);
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-slate-50 dark:bg-slate-900 relative overflow-hidden px-4">
      {/* Decorative Background */}
      <div className="absolute top-0 left-0 w-full h-64 bg-brand-600 dark:bg-brand-900" />
      <div className="absolute top-48 left-1/2 -translate-x-1/2 w-[800px] h-[800px] bg-white dark:bg-slate-800 rounded-full opacity-10 blur-3xl" />

      <div className="relative z-10 w-full max-w-md bg-white dark:bg-slate-800 rounded-2xl shadow-2xl shadow-slate-200/50 dark:shadow-none border border-slate-100 dark:border-slate-700 p-8">
        
        {/* Logo Section */}
        <div className="flex justify-center -mt-16 mb-6">
          <div className="bg-white dark:bg-slate-800 p-4 rounded-full shadow-lg ring-4 ring-slate-50 dark:ring-slate-900">
            <div className="bg-brand-600 p-3 rounded-full text-white">
              <GraduationCap size={32} />
            </div>
          </div>
        </div>

        <div className="text-center mb-8">
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Student Portal</h2>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-2">
            Enter your SAP ID and registered mobile number to login.
          </p>
        </div>

        {error && (
          <div className="mb-6 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-start gap-3 animate-fade-in">
            <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
            <p className="text-sm text-red-600 dark:text-red-300">{error}</p>
          </div>
        )}

        <form onSubmit={handleRequestOtp} className="space-y-6">
          <div className="space-y-4">
            <Input 
              label="SAP ID (11 Digits)"
              type="text"
              placeholder="e.g. 50001234567"
              value={sapId}
              onChange={(e) => setSapId(e.target.value)}
              icon={<Hash size={16} />}
              maxLength={11}
              autoFocus
            />

            <div className="space-y-1">
              <Input 
                label="Mobile Number"
                type="tel"
                inputMode="numeric"
                placeholder="e.g. 9876543210"
                value={phoneNumber}
                onChange={handlePhoneChange}
                icon={<Phone size={16} />}
                className="text-lg tracking-widest font-mono"
                maxLength={10}
              />
              <p className="text-xs text-slate-400 text-right">
                {phoneNumber.length}/10 digits
              </p>
            </div>
          </div>

          <Button 
            type="submit" 
            className="w-full py-3 text-base" 
            disabled={isLoading || phoneNumber.length !== 10 || sapId.length !== 11}
            icon={isLoading ? null : <Send size={18} />}
          >
            {isLoading ? 'Sending Code...' : 'Send Verification Code'}
          </Button>
        </form>

        <div className="mt-8 pt-6 border-t border-slate-100 dark:border-slate-700 text-center">
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-3">
            Not a student?
          </p>
          <Link 
            to="/login/professor" 
            className="text-sm font-semibold text-brand-600 hover:text-brand-700 dark:text-brand-400 hover:underline"
          >
            Switch to Professor / Admin Login
          </Link>
        </div>
      </div>
      
      <div className="absolute bottom-6 w-full text-center">
        <Link to="/select-user" className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-sm transition-colors">
          ← Back to Role Selection
        </Link>
      </div>
    </div>
  );
};