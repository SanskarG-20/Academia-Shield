import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldCheck, ArrowRight, ArrowLeft, Clock, RefreshCw } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { OtpInput } from '../components/ui/OtpInput';
import { requestStudentOtp, verifyStudentOtp } from '../lib/api';

export const LoginStudentOTP: React.FC = () => {
  const navigate = useNavigate();
  const [otp, setOtp] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [timer, setTimer] = useState(60);
  const [phoneNumber, setPhoneNumber] = useState('');
  const [sapId, setSapId] = useState('');
  const [mockOtp, setMockOtp] = useState('');

  useEffect(() => {
    // Retrieve Login Details
    const storedPhone = localStorage.getItem('tempPhoneNumber');
    const storedSapId = localStorage.getItem('tempSapId');
    const storedMockOtp = localStorage.getItem('tempMockOtp');
    
    if (!storedPhone) {
      navigate('/login/student');
      return;
    }
    setPhoneNumber(storedPhone);
    if (storedSapId) setSapId(storedSapId);
    if (storedMockOtp) setMockOtp(storedMockOtp);

    // Countdown Timer
    const interval = setInterval(() => {
      setTimer((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);

    return () => clearInterval(interval);
  }, [navigate]);

  const handleVerify = async () => {
    if (otp.length !== 6 || !sapId) return;

    setIsLoading(true);
    try {
      const data = await verifyStudentOtp(sapId, otp);
      if (data.requiresProfileSetup) {
        navigate('/student/profile');
      } else {
        navigate('/dashboard');
      }
    } catch (error: any) {
      alert(error.message || 'Invalid or expired OTP.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleResend = async () => {
    if (timer > 0) return;
    setTimer(60);

    if (!sapId) return;

    try {
      const response = await requestStudentOtp(sapId);
      if (response?.mockOtp) {
        setMockOtp(response.mockOtp);
        localStorage.setItem('tempMockOtp', response.mockOtp);
      } else {
        setMockOtp('');
        localStorage.removeItem('tempMockOtp');
      }
    } catch (error: any) {
      alert(error.message || 'Failed to resend OTP.');
    }
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-slate-50 dark:bg-slate-900 relative overflow-hidden px-4">
       <div className="absolute top-0 left-0 w-full h-64 bg-brand-600 dark:bg-brand-900" />
       <div className="absolute top-48 left-1/2 -translate-x-1/2 w-[800px] h-[800px] bg-white dark:bg-slate-800 rounded-full opacity-10 blur-3xl" />

       <div className="relative z-10 w-full max-w-md bg-white dark:bg-slate-800 rounded-2xl shadow-2xl shadow-slate-200/50 dark:shadow-none border border-slate-100 dark:border-slate-700 p-8">
         
         {/* Header */}
         <div className="text-center mb-8">
           <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-brand-50 dark:bg-brand-900/20 text-brand-600 dark:text-brand-400 mb-4 animate-pulse">
             <ShieldCheck size={32} />
           </div>
           <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Security Verification</h2>
           <div className="text-slate-500 dark:text-slate-400 text-sm mt-3 bg-slate-50 dark:bg-slate-900/50 py-3 px-4 rounded-lg border border-slate-100 dark:border-slate-700 inline-block">
             <p>SAP ID: <strong className="text-slate-700 dark:text-slate-200">{sapId}</strong></p>
             <p>OTP sent to: <strong className="text-slate-700 dark:text-slate-200">+91 {phoneNumber}</strong></p>
             {mockOtp && (
               <p className="mt-2 text-amber-600 dark:text-amber-400 font-semibold">
                 Demo OTP: {mockOtp}
               </p>
             )}
           </div>
         </div>

         {/* OTP Input */}
         <div className="space-y-8">
            <OtpInput 
              length={6} 
              onComplete={(code) => setOtp(code)} 
              disabled={isLoading}
            />

            <div className="flex items-center justify-between text-sm">
               <div className={`flex items-center gap-1.5 ${timer > 0 ? 'text-slate-500' : 'text-red-500'}`}>
                 <Clock size={14} />
                 <span>{timer > 0 ? `Expires in 00:${timer.toString().padStart(2, '0')}` : 'Code Expired'}</span>
               </div>
               <button 
                 onClick={handleResend}
                 disabled={timer > 0}
                 className={`flex items-center gap-1.5 font-medium transition-colors ${
                   timer > 0 ? 'text-slate-300 cursor-not-allowed' : 'text-brand-600 hover:text-brand-700 cursor-pointer'
                 }`}
               >
                 <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
                 Resend Code
               </button>
            </div>

            <Button 
              className="w-full py-3 text-base" 
              size="lg"
              disabled={isLoading || otp.length !== 6}
              onClick={handleVerify}
              icon={isLoading ? null : <ArrowRight size={18} />}
            >
              {isLoading ? 'Verifying...' : 'Verify & Login'}
            </Button>
         </div>

         <div className="mt-8 pt-6 border-t border-slate-100 dark:border-slate-700 text-center">
            <button 
              onClick={() => navigate('/login/student')}
              className="text-sm text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 flex items-center justify-center gap-1 mx-auto transition-colors"
            >
              <ArrowLeft size={14} /> Change Credentials
            </button>
         </div>
       </div>
    </div>
  );
};