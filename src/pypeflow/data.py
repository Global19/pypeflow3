
# @author Jason Chin
#
# Copyright (C) 2010 by Jason Chin 
# Copyright (C) 2011 by Jason Chin, Pacific Biosciences
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""

PypeData: This module defines the general interface and class for PypeData Objects. 

"""


from urlparse import urlparse, urljoin
import platform
import os, shutil
from common import * 
import logging
    
class FileNotExistError(PypeError):
    pass

class TypeMismatchError(PypeError):
    pass

def fn(obj):
    return obj.localFileName

class PypeDataObjectBase(PypeObject):
    
    """ 
    Represent the common interface for a PypeData object.
    """

    def __init__(self, URL, **attributes):
        PypeObject.__init__(self, URL, **attributes)
        self._log = logging.Logger('dataobject')
        self.verification = []

    @property
    def timeStamp(self):
        raise NotImplementedError, self.__expr__()

    @property
    def exists(self):
        raise NotImplementedError

    def addVerifyFunction( self, verifyFunction ):
        self.verification.append( verifyFunction )

    def __str__( self ):
        return self.URL


class PypeLocalFile(PypeDataObjectBase):

    """ 
    Represent a PypeData object that can be accessed as a file in a local
    filesystem.

    >>> f = PypeLocalFile("file://localhost/test.txt")
    >>> f.localFileName == "test.txt"
    True
    >>> fn(f)
    'test.txt'
    >>> f = PypeLocalFile("file://localhost/test.txt", False, isFasta = True)
    >>> f.isFasta == True
    True
    """

    supportedURLScheme = ["file"]
    def __init__(self, URL, readOnly = True, **attributes):
        PypeDataObjectBase.__init__(self, URL, **attributes)
        URLParseResult = urlparse(URL)
        self.localFileName = URLParseResult.path[1:]
        self._path = self.localFileName
        self.readOnly = readOnly

    @property
    def timeStamp(self):
        if not os.path.exists(self.localFileName):
            raise FileNotExistError("No such file:%s on %s" % (self.localFileName, platform.node()) )
        return os.stat(self.localFileName).st_mtime 

    @property
    def exists(self):
        return os.path.exists(self.localFileName)
    
    def verify( self ):
        self._log.debug("Verifying contents of %s" % self.URL)
        # Get around the NFS problem
        os.listdir(os.path.dirname(self.path)) 
        
        errors = [ ]
        for verifyFn in self.verification:
            try:
                errors.extend( verifyFn(self.path) )
            except Exception, e:
                errors.append( str(e) )
        if len(errors) > 0:
            for e in errors:
                self._log.error(e)
        return errors
    
    @property
    def path( self ):
        if self._path == None:
            raise IOError, "Must resolve this file (%s) with a context " + \
                            "before you can access .path"
        return self._path
    
    def clean( self ):
        if os.path.exists( self.path ):
            self._log.info("Removing %s" % self.path )
            if os.path.isdir( self.path ):
                shutil.rmtree( self.path )
            else:
                os.remove( self.path )

class PypeHDF5Dataset(PypeDataObjectBase):  #stub for now Mar 17, 2010

    """ 
    Represent a PypeData object that is an HDF5 dataset.
    Not implemented yet.
    """

    supportedURLScheme = ["hdf5ds"]
    def __init__(self, URL, readOnly = True, **attributes):
        PypeDataObjectBase.__init__(self, URL, **attributes)
        URLParseResult = urlparse(URL)
        self.localFileName = URLParseResult.path[1:]
        #the rest of the URL goes to HDF5 DS


class PypeLocalFileCollection(PypeDataObjectBase):  #stub for now Mar 17, 2010

    """ 
    Represent a PypeData object that is a composition of multiple files.
    It will provide a container that allows the tasks to choose one or all file to
    process.
    """

    supportedURLScheme = ["files"]
    def __init__(self, URL, readOnly = True, select = 1, **attributes):
        """
           currently we only support select = 1, 
           namely, we only pass the first file add to the collection to the tasks
        """
        PypeDataObjectBase.__init__(self, URL, **attributes)
        URLParseResult = urlparse(URL)
        self.compositedDataObjName = URLParseResult.path[1:]
        self.localFileName =  None
        self._path = None
        self.readOnly = readOnly
        self.verification = []
        self.localFiles = [] # a list of all files within the obj
        self.select = select

    def addLocalFile(self, pLocalFile):
        if not isinstance(pLocalFile, PypeLocalFile):
            raise TypeMismatchError, "only PypeLocalFile object can be added into PypeLocalFileColletion"
        self.localFiles.append(pLocalFile)
        if self.select == 1:
            self.localFileName = self.localFiles[0].localFileName
            self._path = self.localFileName

    @property
    def timeStamp(self):
        if self.localFileName == None:
            raise PypeError, "No PypeLocalFile is added into the PypeLocalFileColletion yet"
        if not os.path.exists(self.localFileName):
            raise FileNotExistError("No such file:%s on %s" % (self.localFileName, platform.node()) )
        return os.stat(self.localFileName).st_mtime 

    @property
    def exists(self):
        if self.localFileName == None:
            raise PypeError, "No PypeLocalFile is added into the PypeLocalFileColletion yet"
        return os.path.exists(self.localFileName)
        

class PypeSplittableLocalFile(PypeDataObjectBase):
    """ 
    Represent a PypeData object that has two different local file representations:
        (1) A whole file
        (2) Split files
    Such data object can have either a scatter task attached or a gather task attached.
    If a scatter task is attached, the task will be inserted to generate the scattered files.
    If a gather task is attached, the task will be inserted to generate the whole file.
    If neither scatter task nor gather task is specified, then the file is mostly like intermediate data.
    Namely, the whole file representation is not used any place else.
    One can not specify scatter task and gather task for the same object since it will create a loop.
    """
    supportedURLScheme = ["splittablefile"]

    def __init__(self, URL, readOnly = True, nChunk = 1, **attributes):
        PypeDataObjectBase.__init__(self, URL, **attributes)
        URLParseResult = urlparse(URL)
        self.localFileName = URLParseResult.path[1:]
        self._path = self.localFileName
        self.readOnly = readOnly
        self.verification = []
        self._scatterTask = None
        self._gatherTask = None
        self._splittedFiles = []
        self.nChunk = nChunk

        cfURL = "file://%s/%s" % (URLParseResult.netloc, URLParseResult.path) 

        self._completeFile = PypeLocalFile(cfURL, readOnly, **attributes)

        if nChunk == 1:
            self._splittedFiles = [self._completeFile]
        else:
            dirname, basename = os.path.split(self._path)

            for i in range(nChunk):
                chunkBasename = "%03d_%s" % (i, basename)
                if dirname != "":
                    chunkURL = "file://%s/%s/%s" % (URLParseResult.netloc, dirname, chunkBasename) 
                else:
                    chunkURL = "file://%s/%s" % (URLParseResult.netloc, chunkBasename) 

                sFile = PypeLocalFile(chunkURL, readOnly, **attributes)
                self._splittedFiles.append(sFile) 

    def setGatherTask(self, TaskCreator, TaskType, function):
        assert self._scatterTask == None
        inputDataObjs = dict( ( ("sf%03d" % c[0], c[1]) 
                                for c in enumerate(self._splittedFiles) ) )
        outputDataObjs = {"cf": self._completeFile}
        gatherTask = TaskCreator( inputDataObjs = inputDataObjs,
                                  outputDataObjs = outputDataObjs,
                                  URL = "task://gather/%s" % self._path ,
                                  TaskType=TaskType) ( function )
        self._gatherTask = gatherTask

    def setScatterTask(self, TaskCreator, TaskType, function):
        assert self._gatherTask == None
        outputDataObjs = dict( ( ("sf%03d" % c[0], c[1]) 
                                for c in enumerate(self._splittedFiles) ) )
        inputDataObjs = {"cf": self._completeFile}
        scatterTask = TaskCreator( inputDataObjs = inputDataObjs,
                                   outputDataObjs = outputDataObjs,
                                   URL = "task://scatter/%s" % self._path ,
                                   TaskType=TaskType) ( function )
        self._scatterTask = scatterTask

    def getGatherTask(self):
        return self._gatherTask

    def getScatterTask(self):
        return self._scatterTask

    def getSplittedFiles(self):
        return self._splittedFiles

    @property
    def timeStamp(self):
        return self._completeFile.timeStamp

def makePypeLocalFile(aLocalFileName, readOnly = True, **attributes):
    """
    >>> f = makePypeLocalFile("./test.txt")
    >>> f.localFileName == "./test.txt"
    True
    >>> fn(f)
    './test.txt'
    """
    return PypeLocalFile("file://localhost/%s" % aLocalFileName, readOnly, **attributes)

if __name__ == "__main__":
    import doctest
    doctest.testmod()
    
