#!/bin/bash

MAC=$(grep -ioP '(?<=\bBOOTIF=)([0-9A-Fa-f]{2}:){5}([0-9A-Fa-f]{2})\b' /proc/cmdline | sed 's/:/-/g')
SERVER=$(grep -oPz '(?<=\bip=)(\d+\.?){4}:\K(\d+\.?){4}' /proc/cmdline)

echo "\$Template RemoteLog, \"<%pri%>%timestamp% ironic/${MAC} %syslogtag%%msg:::sp-if-no-1st-sp%%msg%\n\"" > /etc/rsyslog.d/10-remote.conf

echo '
$ActionFileDefaultTemplate RemoteLog
$WorkDirectory /var/spool/rsyslog/
$ActionQueueType LinkedList   # use asynchronous processing
$ActionQueueFileName queue # set file name, also enables disk mode
$ActionQueueMaxDiskSpace 1g
$ActionQueueSaveOnShutdown on
$ActionQueueLowWaterMark 2000
$ActionQueueHighWaterMark 8000
$ActionQueueSize              1000000       # Reserve 500Mb memory, each queue element is 512b
$ActionQueueDiscardMark       950000        # If the queue looks like filling, start discarding to not block ssh/login/etc.
$ActionQueueDiscardSeverity   0             # When in discarding mode discard everything.
$ActionQueueTimeoutEnqueue    0             # When in discarding mode do not enable throttling.
$ActionQueueDequeueSlowdown 1000
$ActionQueueWorkerThreads 2
$ActionQueueDequeueBatchSize 128
$ActionResumeRetryCount -1
$ActionResumeInterval 1
' >> /etc/rsyslog.d/10-remote.conf

echo "
# Use TCP protocol
*.*   @@${SERVER}:514;RemoteLog
" >> /etc/rsyslog.d/10-remote.conf
