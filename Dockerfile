FROM python:3.6

# Test repo to use during tests
RUN git clone --bare https://github.com/release-depot/patch_rebaser /repos/upstream_repo ; git config --global user.name "Patch Rebaser Integration" ; git config --global user.email "patchrebaser@example.com"

# Local copy to run the tests from
WORKDIR /patch_rebaser

COPY . /patch_rebaser

RUN pip install -r requirements.txt -r test-requirements.txt
