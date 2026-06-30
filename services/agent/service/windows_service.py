"""
Academia Shield Agent — Windows Service Wrapper

Wraps the core agent logic in a Windows Service so it can run
invisibly in the background, starting on boot.

Requires: pywin32 (pip install pywin32)
"""

import sys
import os

# Ensure agent imports work correctly when running as a service
AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

import servicemanager
import win32serviceutil
import win32service
import win32event
import threading

import agent
from logger import setup_logger

LOGGER = setup_logger()


class AcademiaShieldService(win32serviceutil.ServiceFramework):
    _svc_name_ = "AcademiaShieldAgent"
    _svc_display_name_ = "Academia Shield Enforcement Agent"
    _svc_description_ = "Enforces professor-directed website blocking during active class sessions."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)

    def SvcStop(self):
        """Called when the service is stopped by Windows."""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        LOGGER.info("[Service] Stop signal received from Windows")
        
        # Signal the main agent loop to shut down gracefully
        agent.RUNNING = False
        agent.SYNC_EVENT.set()
        
        # Trigger the wait event to unblock SvcDoRun
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        """Called when the service starts."""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        LOGGER.info("[Service] Academia Shield Windows Service started")

        try:
            # Run the agent in a daemon thread so it doesn't block the service control manager
            agent_thread = threading.Thread(target=agent.main, name="AgentMain")
            agent_thread.daemon = True
            agent_thread.start()

            # Block the service thread until SvcStop is called
            win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)

            # Wait briefly for the agent thread to finish its graceful shutdown
            agent_thread.join(timeout=5.0)
            
        except Exception as e:
            LOGGER.error("[Service] Fatal error: %s", e)
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_ERROR_TYPE,
                servicemanager.PYS_SERVICE_STOPPED,
                (self._svc_name_, str(e))
            )

        LOGGER.info("[Service] Service stopped gracefully")


if __name__ == '__main__':
    if len(sys.argv) == 1:
        # Running via the Service Control Manager
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(AcademiaShieldService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        # Running via command line (install/update/remove/start/stop)
        win32serviceutil.HandleCommandLine(AcademiaShieldService)
