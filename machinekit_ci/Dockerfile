#####################################################################
# Description:  Dockerfile
#
#               This file, 'Dockerfile', implements Debian styled Docker images
#               used for building, testing and running Machinekit-HAL in CI/CD
#               workflows.
#
# Copyright (C) 2020            Jakub Fišer  <jakub DOT fiser AT eryaf DOT com>
#
#   based on original Docker mk-cross-builder images by:
#
# Copyright (C) 2016 - 2019     John Morris  <john AT zultron DOT com>
# Copyright (C) 2016 - 2019     Mick Grant   <arceye AT mgware DOT co DOT uk>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
#
######################################################################

######################################################################
# Machinekit Builder Base Image
#
# This image contains basic package development tools and
# configuration to sync container and host user ID for building a
# bind-mounted source tree

ARG DEBIAN_DISTRO_BASE
FROM ${DEBIAN_DISTRO_BASE} AS machinekit_builder_base

SHELL [ "bash", "-c" ]

###########################
# Generic apt configuration

ENV TERM=dumb

# Apt config:  silence warnings and set defaults
ENV DEBIAN_FRONTEND=noninteractive
ENV DEBCONF_NONINTERACTIVE_SEEN=true
ENV LC_ALL=C.UTF-8
ENV LANGUAGE=C.UTF-8
ENV LANG=C.UTF-8

# Turn off recommends on container OS
RUN printf "%s;\n%s;\n"                 \
    'APT::Install-Recommends "0"'       \
    'APT::Install-Suggests "0"'         \
    > /etc/apt/apt.conf.d/01norecommend

# Add Machinekit Dependencies repository
RUN apt-get update &&                                                             \
    apt-get install -y                                                            \
        curl                                                                      \
        apt-transport-https                                                       \
        ca-certificates &&                                                        \
    curl -1sLf                                                                    \
        'https://dl.cloudsmith.io/public/machinekit/machinekit/cfg/setup/bash.deb.sh' \
        | bash &&                                                                 \
    apt-get clean

# Update system OS
RUN apt-get update &&     \
    apt-get -y upgrade && \
    apt-get clean

####################################
# Set up Machinekit user environment

ENV USER=machinekit

RUN addgroup --gid 1000 ${USER} &&                            \
    adduser --uid 1000 --ingroup ${USER} --home /home/${USER} \
    --shell /bin/bash --disabled-password --gecos "" ${USER}

RUN apt-get update &&        \
    apt-get install -y       \
        sudo                 \
        machinekit-fixuid    \
    && \
    apt-get clean

ARG ENTRYPOINT=actions/dockerImage/entrypoint
COPY ${ENTRYPOINT} /opt/bin/entrypoint

RUN mkdir /opt/environment &&                                     \
    echo "${USER} ALL=(ALL:ALL) NOPASSWD: ALL" >> /etc/sudoers && \
    mkdir -p /etc/fixuid &&                                       \
    printf "user: ${USER}\ngroup: ${USER}\n" > /etc/fixuid/config.yml

ENTRYPOINT [ "/opt/bin/entrypoint" ]

######################################################################

RUN apt-get update          \
    && apt-get install -y   \
        build-essential     \
        fakeroot            \
        devscripts          \
        equivs              \
	lintian \
        python3-debian \
        python3-setuptools \
        python3-pip \
        dpkg-sig \
	git \
        lsb-release && \
    apt-get clean

# Bump this number to force cloning the below repos anew
RUN echo 2

RUN cd /tmp && \
    git clone https://github.com/zultron/docker-registry-client && \
    cd docker-registry-client && \
    python3 setup.py install

RUN cd /tmp && \
    git clone https://github.com/zultron/machinekit-ci.git && \
    cd machinekit-ci/actions/initDeps && \
    python3 setup.py install

######################################################################
# Machinekit Builder Base Cross-builder image
#
# This image adds configuration and tools for cross-building packages
# when host architecture differs from the build architecture

FROM machinekit_builder_base AS machinekit_builder_base_arch

ARG ARCHITECTURE
ENV ARCHITECTURE=${ARCHITECTURE}

RUN if ! dpkg-architecture -e${ARCHITECTURE};    \
    then                                              \
        dpkg --add-architecture ${ARCHITECTURE}; \
    fi

# Ubuntu ports repos for cross-building
RUN if test $(source /etc/os-release; echo $ID) = ubuntu \
            -a ${ARCHITECTURE} != amd64 \
	    -a ${ARCHITECTURE} != i386; then \
	CODENAME=$(source /etc/os-release; echo $VERSION_CODENAME) && \
	sed </etc/apt/sources.list \
	    >/etc/apt/sources.list.d/ubuntu-ports-${ARCHITECTURE}.list \
	    -e "/http:\/\/security/ d"  -e "/^#/ d"  -e "/^$/ d" \
	    -e "s/^deb /deb [arch=${ARCHITECTURE}] /" \
	    -e "s,http://archive.ubuntu.com/ubuntu/,http://ports.ubuntu.com/ubuntu-ports/," && \
        cat /etc/apt/sources.list.d/ubuntu-ports-${ARCHITECTURE}.list && \
	sed -i /etc/apt/sources.list \
	    -e "/^#/ d"  -e "/^$/ d" \
	    -e "s/^deb /deb [arch=amd64] /" && \
        cat /etc/apt/sources.list; \
    fi

# Non-standard exception, using the non-standard crossbuild-essential-i386:amd64
# package in Machinekit/Machinekit Cloudsmith repository
RUN if [[ "$(dpkg --print-architecture)" == "amd64" &&                    \
          "$ARCHITECTURE" == "i386" &&                               \
          "$(lsb_release -cs)" == "stretch" ]];                           \
    then                                                                  \
        apt-get install -y                                                \
            gcc-multilib                                                  \
            g++-multilib &&                                               \
        apt-get clean &&                                                  \
        ln -s x86_64-linux-gnu-objcopy /usr/bin/i686-linux-gnu-objcopy && \
        ln -s x86_64-linux-gnu-objdump /usr/bin/i686-linux-gnu-objdump && \
        ln -s x86_64-linux-gnu-strip /usr/bin/i686-linux-gnu-strip;       \
    fi

RUN if [[ "$(dpkg --print-architecture)" == "amd64" && \
          "$ARCHITECTURE" == "i386" &&            \
          "$(lsb_release -cs)" == "stretch" ]];        \
    then                                               \
        printf "%b"                                    \
               "#!/bin/bash\n"                         \
               "export CC=\"gcc -m32\"\n"              \
               "export CXX=\"g++ -m32\"\n"             \
               "export LDEMULATION=\"elf_i386\"\n"     \
               > /opt/environment/compiler.sh;                        \
    else                                                              \
        printf "%b"                                                   \
               "#!/bin/bash\n"                                        \
               "export CC=$(dpkg-architecture -a${ARCHITECTURE}  \
                            -qDEB_HOST_GNU_TYPE)-gcc\n"               \
               "export CXX=$(dpkg-architecture -a${ARCHITECTURE} \
                            -qDEB_HOST_GNU_TYPE)-g++\n"               \
               > /opt/environment/compiler.sh;                        \
    fi

RUN printf "%b"                                               \
           "#!/bin/bash\n"                                    \
           "set -a\n"                                         \
           "$(dpkg-architecture -a${ARCHITECTURE} -s)\n" \
           "set +a\n"                                         \
           > /opt/environment/dpkg-architecture.sh

# This on Debian 9 Stretch, ARCHITECTURE i386 actually abuses the fact
# that the i686-linux-gnu-gcc does not exists (the $CC is set to 'gcc -m32'),
# so the comparison will fail and '-Werror' will be exported - what is the
# end result we want on Stretch anyway
RUN if ! [[ $(echo -e "$($(dpkg-architecture -a${ARCHITECTURE}     \
                           -qDEB_HOST_GNU_TYPE)-gcc -dumpversion)\n8" | \
            sort -V | head -n1) == "8" ]];                              \
    then                                                                \
        printf "%b"                                                     \
               "#!/bin/bash\n"                                          \
               "export DPKG_CFLAGS=\"${DPKG_CFLAGS} -Werror\"\n"        \
               > /opt/environment/dpkg_flags.sh;                        \
    fi

ENV ARCHITECTURE=${ARCHITECTURE}
ENV IN_MACHINEKIT_BUILDER=1

######################################################################
# Package Master Builder Base Cross-builder image
#
# This image includes build dependencies and build configuration for a
# package.  While the Dockerfile is generic, it is configured to build
# package-specific images.
#
# Add `--build-arg=DEBIAN_DIR=some_dir/debian/` if the `debian/`
# packaging directory is not in the top-level source directory.
#
# Add `--build-arg=SCRIPT_PRE_CMD=.github/docker/script_pre.sh` to run
# a command before installing build deps to e.g. configure packaging
# or other configuration.  Custom scripts and other file inputs must
# be in the `.github/docker/` or `debian/` directories.

FROM machinekit_builder_base_arch \
    AS package_builder_arch

ARG DEBIAN_DIR=debian/
COPY ${DEBIAN_DIR} /tmp/debian/
COPY .github/docker /tmp/.github/docker

ARG SCRIPT_PRE_CMD
RUN if test -n "${SCRIPT_PRE_CMD}"; then \
        cd /tmp && \
        ${SCRIPT_PRE_CMD}; \
    fi

RUN cd /tmp &&                                                                \
    apt-get update &&                                                         \
    mk-build-deps --build-arch=$(dpkg-architecture -qDEB_BUILD_ARCH)          \
                  --host-arch=${ARCHITECTURE}                            \
                  -ir -t                                                      \
        "apt-get -o Debug::pkgProblemResolver=yes --no-install-recommends -y" \
                  ./debian/control                                            \
    && apt-get clean

ARG SCRIPT_POST_CMD
RUN if test -n "${SCRIPT_POST_CMD}"; then \
        cd /tmp && \
        ${SCRIPT_POST_CMD}; \
    fi
