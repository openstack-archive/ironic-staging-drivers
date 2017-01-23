#!/bin/bash
# TODO(pas-ha) rewrite as ansible tasks
block_count=2048
block_size=512

function del_drive {
    drive=`echo ${PART} |awk -F"_" '{print $1}'`
    seek_offsetb=0
    EOD=`echo ${PART} |awk -F"_" '{print $2}'`
    let "seek_offsete = EOD / block_size - block_count"
    for offset in ${seek_offsetb} ${seek_offsete}; do
        dd if=/dev/zero of=/dev/${drive} bs=${block_size} seek=${offset} count=${block_count}
    done
}

PARTS=`lsblk -nbl|awk '$6 ~/part/ {print $1"_"$4"\n"}'`
DISKS=`lsblk -nbl|awk '$6 ~/disk/ {print $1"_"$4"\n"}'`
ALL_DRIVES=`echo -e "${PARTS}\\n${DISKS}"`

for PART in $ALL_DRIVES; do
    del_drive
done
