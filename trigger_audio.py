import paramiko


def run():
    alert_address = "eos-alert-p01"
    alert_username = "tremv"

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.connect(alert_address, username=alert_username)
    stdin, stdout, stderr = client.exec_command("~/eos-alert-p01/bin/play_alert_tremv")

    output = stdout.readlines()
    print(output)
    stdin.close()
    client.close()