#!/usr/bin/perl
use strict;
use warnings;
use SOAP::Lite;
#use SOAP::Lite +trace => 'all';

my $amt_host = shift;
my $amt_port = "16992";
my $amt_proto = 'http';

if ($amt_host =~ /([^:]+):(\d+)/) {
  $amt_host = $1;
  $amt_port = $2;
  if ($amt_port == 16993) {
    $amt_proto = 'https';
  }
}

$main::amt_user = "admin";
$main::amt_pass = $ENV{'AMT_PASSWORD'};
my $amt_debug = 0;
$amt_debug = $ENV{'AMT_DEBUG'} if defined($ENV{'AMT_DEBUG'});

my $amt_command = shift;
$amt_command = "info" if !defined($amt_command);
my $amt_arg = shift;

my $amt_version;

#############################################################################
# data

my @ps = ("S0", "S1", "S2", "S3", "S4", "S5 (soft-off)", "S4/S5", "Off");
my %rcc = (
	"reset"      => "16",
	"powerup"    => "17",
	"powerdown"  => "18",
	"powercycle" => "19",
);

my %rccs = (
	"nop"        => "0",
	"pxe"	     => "1",
	"hd"         => "2",
	"hdsafe"     => "3",
	"diag"       => "4",
	"cd"         => "5",
);
my %rccs_oem = (
	"bios"       => 0xc1,
);

# incomplete list
my %pt_status = (
	0x0  =>  "success",
	0x1  =>  "internal error",
	0x3  =>  "invalid pt_mode",
	0xc  =>  "invalid name",
	0xf  =>  "invalid byte_count",
	0x10  =>  "not permitted",
	0x17  =>  "max limit_reached",
	0x18  =>  "invalid auth_type",
	0x1a  =>  "invalid dhcp_mode",
	0x1b  =>  "invalid ip_address",
	0x1c  =>  "invalid domain_name",
	0x20  =>  "invalid provisioning_state",
	0x22  =>  "invalid time",
	0x23  =>  "invalid index",
	0x24  =>  "invalid parameter",
	0x25  =>  "invalid netmask",
	0x26  =>  "flash write_limit_exceeded",
	0x800  =>  "network if_error_base",
	0x801  =>  "unsupported oem_number",
	0x802  =>  "unsupported boot_option",
	0x803  =>  "invalid command",
	0x804  =>  "invalid special_command",
	0x805  =>  "invalid handle",
	0x806  =>  "invalid password",
	0x807  =>  "invalid realm",
	0x808  =>  "storage acl_entry_in_use",
	0x809  =>  "data missing",
	0x80a  =>  "duplicate",
	0x80b  =>  "eventlog frozen",
	0x80c  =>  "pki missing_keys",
	0x80d  =>  "pki generating_keys",
	0x80e  =>  "invalid key",
	0x80f  =>  "invalid cert",
	0x810  =>  "cert key_not_match",
	0x811  =>  "max kerb_domain_reached",
	0x812  =>  "unsupported",
	0x813  =>  "invalid priority",
	0x814  =>  "not found",
	0x815  =>  "invalid credentials",
	0x816  =>  "invalid passphrase",
	0x818  =>  "no association",
);


#############################################################################
# soap setup

my ($nas, $sas, $rcs);

sub SOAP::Transport::HTTP::Client::get_basic_credentials {
	return $main::amt_user => $main::amt_pass;
}

sub soap_init() {
	my $proxybase = "$amt_proto://$amt_host:$amt_port";
	my $schemabase = "http://schemas.intel.com/platform/client";

	$nas = SOAP::Lite->new(
		proxy      => "$proxybase/NetworkAdministrationService",
		default_ns => "$schemabase/NetworkAdministration/2004/01");
	$sas = SOAP::Lite->new(
		proxy      => "$proxybase/SecurityAdministrationService",
		default_ns => "$schemabase/SecurityAdministration/2004/01");
	$rcs = SOAP::Lite->new(
		proxy      => "$proxybase/RemoteControlService",
		default_ns => "$schemabase/RemoteControl/2004/01");

	$nas->autotype(0);
	$sas->autotype(0);
	$rcs->autotype(0);

	$amt_version = $sas->GetCoreVersion()->paramsout;
}


#############################################################################
# functions

sub usage() {
	print STDERR <<EOF;

This utility can talk to Intel AMT managed machines.

usage: amttool <hostname> [ <command> ] [ <arg(s)> ]
commands:
   info            - print some machine info (default).
   reset           - reset machine.
   powerup         - turn on machine.
   powerdown       - turn off machine.
   powercycle      - powercycle machine.
   powerinfo       - print power status

AMT 2.5+ only:
   netinfo         - print network config.
   netconf <args>  - configure network (check manpage).

Password is passed via AMT_PASSWORD environment variable.

EOF
}

sub print_result($) {
	my $ret = shift;
	my $rc = $ret->result;
	my $msg;

	if (!defined($rc)) {
		$msg = "soap failure";
	} elsif (!defined($pt_status{$rc})) {
		$msg = sprintf("unknown pt_status code: 0x%x", $rc);
	} else {
		$msg = "pt_status: " . $pt_status{$rc};
	}
	printf "result: %s\n", $msg;
}

sub print_paramsout($) {
	my $ret = shift;
	my @paramsout = $ret->paramsout;
	print "params: " . join(", ", @paramsout) . "\n";
}

sub print_hash {
	my $hash = shift;
	my $in = shift;
	my $wi = shift;

	foreach my $item (sort keys %{$hash}) {
		if (ref($hash->{$item}) eq "HASH") {
#			printf "%*s%s\n", $in, "", $item;
			next;
		}
		printf "%*s%-*s%s\n", $in, "", $wi, $item, $hash->{$item};
	}
}

sub print_hash_ipv4 {
	my $hash = shift;
	my $in = shift;
	my $wi = shift;

	foreach my $item (sort keys %{$hash}) {
		my $addr = sprintf("%d.%d.%d.%d",
			$hash->{$item} / 256 / 256 / 256,
			$hash->{$item} / 256 / 256 % 256,
			$hash->{$item} / 256 % 256,
			$hash->{$item} % 256);
		printf "%*s%-*s%s\n", $in, "", $wi, $item, $addr;
	}
}

sub do_soap {
	my $soap = shift;
	my $name = shift;
	my @args = @_;
	my $method;

	$method = SOAP::Data->name($name)
			    ->attr( { xmlns => $soap->ns } );

	if ($amt_debug) {
		print "-- \n";
		open XML, "| xmllint --format -";
		print XML $soap->serializer->envelope(method => $method, @_);
		close XML;
		print "-- \n";
	}

	my $ret = $soap->call($method, @args);
	print_result($ret);
	return $ret;
}

sub check_amt_version {
	my $major = shift;
	my $minor = shift;

	$amt_version =~ m/^(\d+).(\d+)/;
	return if $1 > $major;
	return if $1 == $major && $2 >= $minor;
	die "version mismatch (need >= $major.$minor, have $amt_version)";
}

sub print_general_info() {
	printf "### AMT info on machine '%s' ###\n", $amt_host;

	printf "AMT version:  %s\n", $amt_version;
	
	my $hostname = $nas->GetHostName()->paramsout;
	my $domainname = $nas->GetDomainName()->paramsout;
	printf "Hostname:     %s.%s\n", $hostname, $domainname;

	my $powerstate = $rcs->GetSystemPowerState()->paramsout;
	printf "Powerstate:   %s\n", $ps [ $powerstate & 0x0f ];
}

sub print_power_info() {
	my $powerstate = $rcs->GetSystemPowerState()->paramsout;
	printf "Powerstate:   %s\n", $ps [ $powerstate & 0x0f ];
}

sub print_remote_info() {
	my @rccaps = $rcs->GetRemoteControlCapabilities()->paramsout;
	printf "Remote Control Capabilities:\n";
	printf "    IanaOemNumber                   %x\n", $rccaps[0];
	printf "    OemDefinedCapabilities          %s%s%s%s%s\n",
		$rccaps[1] & 0x01 ? "IDER "        : "",
		$rccaps[1] & 0x02 ? "SOL "         : "",
		$rccaps[1] & 0x04 ? "BiosReflash " : "",
		$rccaps[1] & 0x08 ? "BiosSetup "   : "",
		$rccaps[1] & 0x10 ? "BiosPause "   : "";

	printf "    SpecialCommandsSupported        %s%s%s%s%s\n",
		$rccaps[2] & 0x0100 ? "PXE-boot "         : "",
		$rccaps[2] & 0x0200 ? "HD-boot "          : "",
		$rccaps[2] & 0x0400 ? "HD-boot-safemode " : "",
		$rccaps[2] & 0x0800 ? "diag-boot "        : "",
		$rccaps[2] & 0x1000 ? "cd-boot "          : "";

	printf "    SystemCapabilitiesSupported     %s%s%s%s\n",
		$rccaps[3] & 0x01 ? "powercycle " : "",
		$rccaps[3] & 0x02 ? "powerdown "  : "",
		$rccaps[3] & 0x03 ? "powerup "    : "",
		$rccaps[3] & 0x04 ? "reset "      : "";

	printf "    SystemFirmwareCapabilities      %x\n", $rccaps[4];
}

sub print_network_info() {
	my $ret;

	$ret = $nas->EnumerateInterfaces();
	my @if = $ret->paramsout;
	foreach my $if (@if) {
		printf "Network Interface %s:\n", $if;
		my $arg = SOAP::Data->name('InterfaceHandle' => $if);
		$ret = $nas->GetInterfaceSettings($arg);
		my $desc = $ret->paramsout;
		print_hash($ret->paramsout, 4, 32);
		print_hash_ipv4($ret->paramsout->{'IPv4Parameters'}, 8, 28);
	}
}

sub remote_control($$) {
	my $command = shift;
	my $special = shift;
	my @args;

	my $hostname = $nas->GetHostName()->paramsout;
	my $domainname = $nas->GetDomainName()->paramsout;
    push (@args, SOAP::Data->name('Command' => $rcc{$command}));
    push (@args, SOAP::Data->name('IanaOemNumber' => 343));
    if (defined($special) && defined($rccs{$special})) {
        push (@args, SOAP::Data->name('SpecialCommand' 
                          => $rccs{$special} ));
    }
    if (defined($special) && defined($rccs_oem{$special})) {
        push (@args, SOAP::Data->name('SpecialCommand' 
                          => $rccs_oem{$special} ));
        push (@args, SOAP::Data->name('OEMparameters' => 1 ));
    }
    do_soap($rcs, "RemoteControl", @args);
}

sub ipv4_addr($$) {
	my $name = shift;
	my $ipv4 = shift;

	$ipv4 =~ m/(\d+).(\d+).(\d+).(\d+)/ or die "parse ipv4 address: $ipv4";
	my $num = $1 * 256 * 256 * 256 +
		$2 * 256 * 246 +
		$3 * 256 +
		$4;
	printf STDERR "ipv4 %-24s: %-16s -> %d\n", $name, $ipv4, $num
		if $amt_debug;
	return SOAP::Data->name($name => $num);
}

sub configure_network {
	my $if = shift;
	my $link = shift;
	my $ip = shift;
	my $mask = shift;
	my $gw = shift;
	my $dns1 = shift;
	my $dns2 = shift;

	my $mode;
	my @ifdesc;
	my @ipv4;

	my $method;
	my @args;

	# build argument structs ...
	die "no interface" if !defined($if);
	die "no linkpolicy" if !defined($link);
	if (defined($ip)) {
		$mode = "SEPARATE_MAC_ADDRESS";
		die "no ip mask"     if !defined($mask);
		die "no default gw"  if !defined($gw);
		$dns1 = $gw          if !defined($dns1);
		$dns2 = "0.0.0.0"    if !defined($dns2);
		push (@ipv4, ipv4_addr("LocalAddress", $ip));
		push (@ipv4, ipv4_addr("SubnetMask", $mask));
		push (@ipv4, ipv4_addr("DefaultGatewayAddress", $gw));
		push (@ipv4, ipv4_addr("PrimaryDnsAddress", $dns1));
		push (@ipv4, ipv4_addr("SecondaryDnsAddress", $dns2));
	} else {
		$mode = "SHARED_MAC_ADDRESS";
		# no ip info -- use DHCP
	}

	push (@ifdesc, SOAP::Data->name("InterfaceMode" => $mode));
	push (@ifdesc, SOAP::Data->name("LinkPolicy" => $link));
	push (@ifdesc, SOAP::Data->name("IPv4Parameters" => 
		\SOAP::Data->value(@ipv4)))
			if @ipv4;

	push (@args, SOAP::Data->name("InterfaceHandle" => $if));
	push (@args, SOAP::Data->name("InterfaceDescriptor" =>
		\SOAP::Data->value(@ifdesc)));

	# perform call
	do_soap($nas, "SetInterfaceSettings", @args);
}


#############################################################################
# main

if (!defined($amt_host)) {
	usage();
	exit 1;
}

soap_init;

if ($amt_command eq "info") {
	print_general_info;
	print_remote_info;
} elsif ($amt_command eq "netinfo") {
	check_amt_version(2,5);
	print_network_info;
} elsif ($amt_command eq "netconf") {
	check_amt_version(2,5);
	configure_network(@ARGV);
} elsif ($amt_command eq "powerinfo") {
    print_power_info;
} elsif ($amt_command =~ m/^(reset|powerup|powerdown|powercycle)$/) {
	remote_control($amt_command, $amt_arg);
} else {
	print "unknown command: $amt_command\n";
}

