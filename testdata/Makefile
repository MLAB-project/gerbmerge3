all: merge1.xln merge2.xln

merge1.xln:
	gerbmerge layout1.cfg layout1.xml

merge2.xln:
	gerbmerge layout2.cfg layout2.xml

view1:
	gerbv merge1.* &

view2:
	gerbv merge2.* &

clean:
	-rm -f merge1.* merge2.* toollist.* placement.*

# Demonstrates randomized search
random:
	-rm -f merge2.*
	-gerbmerge layout2.cfg

# vim: noexpandtab
