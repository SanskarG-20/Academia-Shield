!macro customInstall
  ExecWait '"$INSTDIR\resources\agent\AcademiaShield.exe" --install-only' $0
  IntCmp $0 0 done
    MessageBox MB_ICONSTOP "The Academia Shield agent could not be installed. The setup will stop; check administrator permissions and try again."
    Abort
  done:
!macroend

!macro customUnInstall
  IfFileExists "$INSTDIR\resources\agent\AcademiaShield.exe" 0 done
    ExecWait '"$INSTDIR\resources\agent\AcademiaShield.exe" --uninstall' $0
    IntCmp $0 0 done
      MessageBox MB_ICONSTOP "The agent could not safely restore its managed settings. The uninstall will stop so recovery files remain available."
      Abort
  done:
!macroend
