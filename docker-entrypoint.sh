#!/bin/sh

print_info() {
    printf "\033[1m[$0] [-]\033[0m %s\n" "$1"
}

print_error() {
    printf "\033[31;1m[$0] [!]\033[0m %s\n" "$1"
}

if [ -n "${FORCE_UPDATE_CA_CERTIFICATES}" ];
then
  if [ "$(id -u)" -ne "0" ];
  then
    print_error "update-ca-certificates requires to be run as root"
    exit 1
  fi

  print_info "Provisioning additional certificates"

  update-ca-certificates
  rm /etc/ssl/cert.pem
  ln -s /etc/ssl/certs/ca-certificates.crt /etc/ssl/cert.pem
fi

if [ "$(id -u)" -eq "0" ];
then
  print_info "Dropping privileges"
  su - nonroot
fi

print_info "$(printf "%s " "Running server with arguments:" "${@}")"
exec /usr/local/bin/python -m uvicorn project.main:app "${@}"
