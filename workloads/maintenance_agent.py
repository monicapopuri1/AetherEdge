import psutil
import json
import socket

def run_analysis():
    # 1. Gather Raw Data
    disk_usage = psutil.disk_usage('/').percent
    mem_usage = psutil.virtual_memory().percent
    cpu_usage = psutil.cpu_percent(interval=1)
    
    # 2. Edge Logic (The "Intelligence")
    status = "HEALTHY"
    recommendation = "No action required."
    
    if disk_usage > 85:
        status = "CRITICAL"
        recommendation = "Clear log files immediately to prevent node crash."
    elif cpu_usage > 90:
        status = "WARNING"
        recommendation = "High compute load detected. Consider offloading tasks."

    # 3. Format Result
    result = {
        "node_name": socket.gethostname(),
        "status": status,
        "metrics": {
            "cpu": cpu_usage,
            "disk": disk_usage,
            "memory": mem_usage
        },
        "recommendation": recommendation
    }
    return json.dumps(result)

if __name__ == "__main__":
    print(run_analysis())