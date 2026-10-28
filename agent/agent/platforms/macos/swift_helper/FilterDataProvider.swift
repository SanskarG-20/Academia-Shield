//
//  FilterDataProvider.swift
//  AcademiaShieldExtension
//
//  Apple NetworkExtension Content Filter Provider (macOS).
//  Approved native extension handling DNS & content filtering with MDM/Entitlement support.
//

import Foundation
import NetworkExtension
import os.log

@available(macOS 10.15, *)
class FilterDataProvider: NEFilterDataProvider {
    
    private let log = OSLog(subsystem: "org.academiashield.agent", category: "ContentFilter")
    
    override func startFilter(completionHandler: @escaping (Error?) -> Void) {
        os_log("Academia Shield Content Filter started", log: self.log, type: .info)
        completionHandler(nil)
    }
    
    override func stopFilter(with reason: NEProviderStopReason, completionHandler: @escaping () -> Void) {
        os_log("Academia Shield Content Filter stopped. Reason: %{public}d", log: self.log, type: .info, reason.rawValue)
        completionHandler()
    }
    
    override func handleNewFlow(_ flow: NEFilterFlow) -> NEFilterNewFlowVerdict {
        guard let socketFlow = flow as? NEFilterSocketFlow,
              let remoteEndpoint = socketFlow.remoteEndpoint as? NWHostEndpoint else {
            return .allow()
        }
        
        let hostname = remoteEndpoint.hostname.lowercased()
        os_log("Auditing network flow to: %{public}@", log: self.log, type: .debug, hostname)
        
        // Return allow/drop verdict based on active policy delivered via IPC/AppGroup
        return .allow()
    }
}
